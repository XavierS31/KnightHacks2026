"""Read-only, bounded source snapshots. Source text is data, never instructions."""
import asyncio
import base64
import binascii
import hashlib
import re
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
from fastapi import HTTPException
from pydantic import Field, field_validator

from backend.app.features.integration.discovery import discovery_error
from backend.app.shared.contracts import Contract, Repository

MAX_RESPONSE_BYTES = 512_000
MAX_FILE_BYTES = 100_000
MAX_TEXT_CHARS = 20_000


class SourceRequest(Contract):
    documentation_paths: list[str] = Field(default_factory=list, max_length=3)
    issue_limit: int = Field(default=5, ge=0, le=10)

    @field_validator("documentation_paths")
    @classmethod
    def safe_paths(cls, paths):
        if len(set(paths)) != len(paths):
            raise ValueError("Documentation paths must be unique")
        for path in paths:
            if (len(path) > 200 or not re.fullmatch(r"[A-Za-z0-9_. /-]+", path)
                    or any(part in {"", ".", ".."} for part in path.split("/"))
                    or not path.lower().endswith((".md", ".rst", ".txt"))):
                raise ValueError("Use relative Markdown, RST or text documentation paths")
        return paths


class SourceDocument(Contract):
    kind: Literal["readme", "license", "documentation", "issue"]
    reference: str
    request_reference: str
    collected_at: datetime
    path: str | None = None
    blob_sha: str | None = None
    text: str
    content_sha256: str
    truncated: bool


class SourceSnapshot(Contract):
    id: UUID
    repository_id: UUID
    full_name: str
    commit_sha: str
    commit_reference: str
    collected_at: datetime
    status: Literal["collected", "partial"]
    license_spdx: str | None
    documents: list[SourceDocument]
    limitations: list[str]
    failures: list[str]
    storage: Literal["in_memory", "database"] = "in_memory"


class GitHubSources:
    async def _json(self, client, path, params=None, missing_ok=False):
        try:
            async with client.stream("GET", f"https://api.github.com{path}", params=params) as response:
                if response.status_code == 404 and missing_ok:
                    return None, str(response.request.url)
                if response.status_code in {403, 429}:
                    raise discovery_error(429, "GITHUB_RATE_LIMIT", "GitHub refused source collection.", True)
                if response.status_code != 200:
                    raise discovery_error(502, "GITHUB_SOURCE_FAILED", "GitHub source read failed.", True)
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        raise discovery_error(502, "GITHUB_SOURCE_TOO_LARGE", "Source response exceeds the byte limit.")
                    chunks.append(chunk)
                payload = httpx.Response(200, content=b"".join(chunks)).json()
                return payload, str(response.request.url)
        except httpx.RequestError as exc:
            raise discovery_error(502, "GITHUB_UNAVAILABLE", "GitHub source collection is unavailable.", True) from exc
        except ValueError as exc:
            raise discovery_error(502, "GITHUB_INVALID_RESPONSE", "GitHub returned malformed source data.") from exc

    @staticmethod
    def _document(payload, name, sha, kind, request_reference):
        path = payload["path"]
        if (payload.get("type") != "file" or payload.get("encoding") != "base64"
                or not isinstance(path, str) or not path
                or any(part in {"", ".", ".."} for part in path.split("/"))):
            raise ValueError("Invalid file")
        size = payload["size"]
        if type(size) is not int or size < 0 or size > MAX_FILE_BYTES:
            raise ValueError("File exceeds limit")
        blob_sha = payload["sha"]
        if not isinstance(blob_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", blob_sha):
            raise ValueError("Invalid blob identity")
        raw = base64.b64decode("".join(payload["content"].split()), validate=True)
        if len(raw) != size or len(raw) > MAX_FILE_BYTES:
            raise ValueError("Invalid file size")
        # Git object identity binds the decoded file to the API's blob identity.
        if hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest() != blob_sha:
            raise ValueError("Blob identity mismatch")
        text = raw.decode("utf-8")
        return SourceDocument(
            kind=kind, path=path, blob_sha=blob_sha,
            reference=f"https://github.com/{name}/blob/{sha}/{quote(path, safe='/')}",
            request_reference=request_reference, collected_at=datetime.now(UTC),
            text=text[:MAX_TEXT_CHARS], content_sha256=hashlib.sha256(raw).hexdigest(),
            truncated=len(text) > MAX_TEXT_CHARS,
        )

    async def collect(self, repository: Repository, request: SourceRequest, token="", transport=None):
        name = repository.full_name
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
            raise discovery_error(422, "INVALID_REPOSITORY", "Invalid GitHub repository identity.")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        base = f"/repos/{name}"
        async with httpx.AsyncClient(headers=headers, timeout=15, follow_redirects=False,
                                     transport=transport) as client:
            metadata, _ = await self._json(client, base)
            commits, _ = await self._json(client, f"{base}/commits", {"per_page": 1})
            try:
                if metadata["full_name"].lower() != name.lower():
                    raise ValueError("Repository mismatch")
                sha = commits[0]["sha"]
                if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
                    raise ValueError("Invalid commit")
                license_info = metadata.get("license")
                spdx = license_info.get("spdx_id") if isinstance(license_info, dict) else None
                if spdx is not None and not isinstance(spdx, str):
                    raise ValueError("Invalid license metadata")
            except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
                raise discovery_error(502, "GITHUB_INVALID_RESPONSE", "Cannot establish a source commit.") from exc
            documents, failures = [], []
            files = [("readme", f"{base}/readme"), ("license", f"{base}/license")]
            files += [("documentation", f"{base}/contents/{quote(path, safe='/')}")
                      for path in request.documentation_paths]
            for kind, path in files:
                try:
                    payload, url = await self._json(client, path, {"ref": sha}, missing_ok=True)
                    if payload is None:
                        failures.append(f"{kind}: requested source is missing.")
                    else:
                        documents.append(self._document(payload, name, sha, kind, url))
                except HTTPException as exc:
                    failures.append(f"{kind}: {exc.detail['code']}")
                    if exc.status_code == 429:
                        break
                except (ValueError, TypeError, KeyError, AttributeError, binascii.Error):
                    failures.append(f"{kind}: invalid, unsupported or oversized source file.")
            if request.issue_limit and not any("GITHUB_RATE_LIMIT" in failure for failure in failures):
                try:
                    issues, url = await self._json(client, f"{base}/issues", {
                        "state": "all", "sort": "updated", "direction": "desc",
                        "per_page": request.issue_limit,
                    })
                    if not isinstance(issues, list):
                        raise ValueError("Invalid issue response")
                    for issue in issues[:request.issue_limit]:
                        if not isinstance(issue, dict):
                            raise ValueError("Invalid issue")
                        if "pull_request" in issue:
                            continue
                        number, title, body = issue["number"], issue["title"], issue.get("body")
                        if type(number) is not int or number < 1 or not isinstance(title, str):
                            raise ValueError("Invalid issue identity")
                        if body is not None and not isinstance(body, str):
                            raise ValueError("Invalid issue body")
                        text = title + "\n\n" + (body or "")
                        documents.append(SourceDocument(
                            kind="issue", reference=f"https://github.com/{name}/issues/{number}",
                            request_reference=url, collected_at=datetime.now(UTC),
                            text=text[:MAX_TEXT_CHARS], content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                            truncated=len(text) > MAX_TEXT_CHARS,
                        ))
                except HTTPException as exc:
                    failures.append(f"issues: {exc.detail['code']}")
                except (ValueError, TypeError, KeyError):
                    failures.append("issues: malformed source records; collected subset retained.")
        return SourceSnapshot(
            id=uuid4(), repository_id=repository.id, full_name=name, commit_sha=sha,
            commit_reference=f"https://github.com/{name}/commit/{sha}",
            collected_at=datetime.now(UTC), status="partial" if failures else "collected",
            license_spdx=spdx, documents=documents, failures=failures,
            limitations=[
                "Source text is untrusted; no code execution or model extraction occurred.",
                "Files are commit-pinned; issues and SPDX metadata are collection-time snapshots.",
                "License metadata is not a license approval; inspect the pinned license before selection.",
                "Only README, license and explicitly requested documentation are read; no recursive crawl.",
                "One bounded issue page is sampled; pull requests are excluded without backfilling.",
                "Text may be truncated; SHA-256 identifies full decoded content, not the displayed excerpt.",
                "Metadata and documentation do not establish validated capabilities or feasibility.",
            ],
        )


class SourceStore:
    """Retain at most 100 snapshots in this process. They are also stored when records exist."""

    def __init__(self):
        self.snapshots: OrderedDict[UUID, SourceSnapshot] = OrderedDict()
        self.github = GitHubSources()

    async def create(self, run_id, repository, request, token="", records=None):
        snapshot = await self.github.collect(repository, request, token)
        return await asyncio.to_thread(self.add, run_id, snapshot, records)

    def add(self, run_id, snapshot, records=None):
        if records is not None:
            snapshot = snapshot.model_copy(update={"storage": "database", "limitations": [
                *snapshot.limitations, "The snapshot is stored in the database with its run and commit."]})
            records.save_snapshot(run_id, snapshot)
        else:
            snapshot = snapshot.model_copy(update={"limitations": [
                *snapshot.limitations, "In-memory snapshots are lost on restart or after 100 newer snapshots."]})
        self.snapshots[snapshot.id] = snapshot
        while len(self.snapshots) > 100:
            self.snapshots.popitem(last=False)
        return snapshot

    def get(self, snapshot_id, records=None):
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None and records is not None:
            snapshot = records.get_snapshot(snapshot_id)
        if snapshot is None:
            raise discovery_error(404, "SOURCE_SNAPSHOT_NOT_FOUND", "Snapshot is unknown or no longer retained.")
        return snapshot
