"""Bounded read-only GitHub discovery. The search cache stays in memory; live runs may be stored."""
import asyncio
import re
from collections import OrderedDict
from datetime import UTC, date, datetime
from time import monotonic
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
from fastapi import HTTPException
from pydantic import Field, field_validator, model_validator

from backend.app.shared.contracts import Contract, Evidence, Repository
from backend.app.shared.fixtures import REPOSITORIES

GITHUB_SEARCH = "https://api.github.com/search/repositories"


class DiscoveryRequest(Contract):
    mode: Literal["fixture", "live"] = "fixture"
    discovery_mode: Literal["popular", "trending"] = "popular"
    created_after: date | None = None
    pushed_after: date | None = None
    trending_period: Literal["daily", "weekly", "monthly"] = "weekly"
    trending_language: str = Field(default="", max_length=32)

    @field_validator("trending_language")
    @classmethod
    def language_slug(cls, value):
        if value and not re.fullmatch(r"[a-z0-9+#.-]+", value):
            raise ValueError("Use a lowercase GitHub Trending language slug")
        return value

    @model_validator(mode="after")
    def dates_only_for_search(self):
        if self.discovery_mode == "trending" and (self.created_after or self.pushed_after):
            raise ValueError("Date filters belong to Popular search, not Trending snapshots")
        return self
    query: str = Field(default="language:Python", min_length=1, max_length=200)
    limit: int = Field(default=20, ge=1, le=30)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        if not value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("Use a nonempty, single-line GitHub search query")
        return value.strip()


class DiscoveryRun(Contract):
    id: UUID
    mode: Literal["fixture", "live"]
    status: Literal["fixture", "completed"]
    request: DiscoveryRequest
    created_at: datetime
    repositories: list[Repository]
    source_total: int | None = None
    cache_hit: bool = False
    source_collected_at: datetime
    storage: Literal["in_memory", "database"] = "in_memory"
    limitations: list[str]
    next_gate: str


def discovery_error(status: int, code: str, message: str, retryable: bool = False):
    return HTTPException(status_code=status, detail={
        "code": code, "message": message, "retryable": retryable,
    })


class GitHubDiscovery:
    """One search request per run, fixed host, bounded timeout, five-minute memory cache."""

    def __init__(self):
        self.cache: OrderedDict[tuple[str, int], tuple[float, datetime, list[Repository], int]] = OrderedDict()

    async def search(self, request: DiscoveryRequest, token: str = "", transport=None):
        query = request.query
        if request.created_after:
            query += f" created:>={request.created_after.isoformat()}"
        if request.pushed_after:
            query += f" pushed:>={request.pushed_after.isoformat()}"
        key = (query, request.limit)
        now = monotonic()
        cached = self.cache.get(key)
        if cached and now - cached[0] < 300:
            self.cache.move_to_end(key)
            return cached[2], cached[3], cached[1], True
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        params = {"q": f"{query} archived:false fork:false", "sort": "stars",
                  "order": "desc", "per_page": request.limit, "page": 1}
        try:
            async with httpx.AsyncClient(timeout=15, transport=transport, follow_redirects=False) as client:
                response = await client.get(GITHUB_SEARCH, params=params, headers=headers)
        except httpx.RequestError as exc:
            raise discovery_error(502, "GITHUB_UNAVAILABLE", "GitHub discovery is unavailable.", True) from exc
        if response.status_code in (403, 429):
            raise discovery_error(429, "GITHUB_RATE_LIMIT", "GitHub refused the request; check quota or permissions.", True)
        if response.status_code == 401:
            raise discovery_error(502, "GITHUB_AUTH_FAILED", "GitHub authentication failed; check server configuration.")
        if response.status_code != 200:
            raise discovery_error(502, "GITHUB_UPSTREAM_ERROR", "GitHub returned an unsuccessful response.", True)
        collected_at = datetime.now(UTC)
        try:
            payload = response.json()
            if payload.get("incomplete_results") is not False:
                raise ValueError("Incomplete search")
            items = payload["items"]
            total = payload["total_count"]
            if not isinstance(items, list) or type(total) is not int or total < 0:
                raise ValueError("Invalid search")
            repositories = [self._repository(item, str(response.request.url), collected_at)
                            for item in items[:request.limit]]
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise discovery_error(502, "GITHUB_INVALID_RESPONSE", "GitHub metadata did not match the expected schema.", True) from exc
        self.cache[key] = (now, collected_at, repositories, total)
        self.cache.move_to_end(key)
        while len(self.cache) > 20:
            self.cache.popitem(last=False)
        return repositories, total, collected_at, False

    @staticmethod
    def _repository(item, reference: str, collected_at: datetime) -> Repository:
        name = item["full_name"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
            raise ValueError("Invalid repository identity")
        stars = item["stargazers_count"]
        if type(stars) is not int or stars < 0:
            raise ValueError("Invalid star count")
        description = item.get("description")
        if description is not None and not isinstance(description, str):
            raise ValueError("Invalid description")
        return Repository(
            id=uuid5(NAMESPACE_URL, f"https://github.com/{name.lower()}"),
            full_name=name, url=f"https://github.com/{name}", stars=stars,
            description=(description or "No description supplied by the repository.")[:2000],
            discovery_mode="popular", commit_sha=None,
            evidence=[Evidence(source="GitHub repository search API", reference=reference,
                               collected_at=collected_at, kind="source",
                               note="Repository metadata from star-sorted search; no commit, interface or execution validation.")],
        )


class DiscoveryStore:
    """Retain at most 100 runs in this process. Live runs are also stored when records exist."""

    def __init__(self):
        self.runs: OrderedDict[UUID, DiscoveryRun] = OrderedDict()
        self.github = GitHubDiscovery()

    async def create(self, request: DiscoveryRequest, token: str = "", records=None) -> DiscoveryRun:
        now = datetime.now(UTC)
        if request.mode == "fixture":
            repositories, total, collected_at, hit = REPOSITORIES[:request.limit], None, now, False
        elif request.discovery_mode == "trending":
            from backend.app.features.integration.trending import trending_snapshot
            repositories, total, collected_at, hit = await trending_snapshot(request, token)
        else:
            repositories, total, collected_at, hit = await self.github.search(request, token)
        limitations = []
        if request.mode == "fixture":
            limitations.append("Synthetic fixture only: no GitHub request or model inference occurred.")
        limitations += [
            "Trending is a timestamped GitHub page snapshot; ranking can change."
            if request.discovery_mode == "trending"
            else "Popular means star-sorted search; this is not Trending.",
            "Metadata does not prove capability, feasibility, novelty or integration.",
            "Search metadata excludes source inspection and proposal inference; inspect candidates separately.",
        ]
        if request.discovery_mode == "trending":
            limitations.append("A bounded page is sampled; fork/archived entries are excluded without backfilling.")
        run = DiscoveryRun(
            id=uuid4(), mode=request.mode, status="fixture" if request.mode == "fixture" else "completed",
            request=request, created_at=now, repositories=repositories, source_total=total,
            cache_hit=hit, source_collected_at=collected_at, limitations=limitations,
            next_gate="Inspect source interfaces and pin commits before proposing a real adapter.",
        )
        # The database write blocks, so it runs off the event loop.
        return await asyncio.to_thread(self.add, run, records)

    def add(self, run: DiscoveryRun, records=None) -> DiscoveryRun:
        """Retain the run. Store a live run first when records exist; fixture runs stay in memory."""
        if records is not None and run.mode == "live":
            run = run.model_copy(update={"storage": "database", "limitations": [
                "The run record is stored in the database; the five-minute search cache is not.",
                *run.limitations]})
            records.save_run(run)
        else:
            run = run.model_copy(update={"limitations": [
                "In-memory run records expire on restart or after 100 newer runs.", *run.limitations]})
        self.runs[run.id] = run
        while len(self.runs) > 100:
            self.runs.popitem(last=False)
        return run

    def get(self, run_id: UUID, records=None) -> DiscoveryRun:
        run = self.runs.get(run_id)
        if run is None and records is not None:
            run = records.get_run(run_id)
        if run is None:
            raise discovery_error(404, "DISCOVERY_RUN_NOT_FOUND", "Run is unknown or no longer retained.")
        return run
