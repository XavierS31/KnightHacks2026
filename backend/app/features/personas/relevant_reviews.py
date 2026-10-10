"""Bounded public upstream issue intake; source bodies stay transient and untrusted."""

import json
import re
from datetime import UTC, datetime

import httpx

from .review_corpus import (
    CollectedReview,
    ReviewSourceError,
    normalize_text,
)

GITHUB_API = "https://api.github.com"
ACCESS_BASIS = (
    "Public, unauthenticated fixed issue GET documented at "
    "https://docs.github.com/en/rest/issues/issues#get-an-issue; GitHub API terms and "
    "privacy reviewed 2026-10-10 at https://docs.github.com/en/site-policy/github-terms/"
    "github-terms-of-service and https://docs.github.com/en/site-policy/privacy-policies/"
    "github-general-privacy-statement. No training, author retention or bulk redistribution; "
    "retain factual paraphrases, hashes, permalinks and <=25-word support excerpts only. "
    "Public access does not imply a blanket content license."
)

async def collect_public_issue(
    repository: str, number: int, *, software_context: str, selection_context: str,
    access_basis: str, allowed_repositories: frozenset[str] | None = None, client: httpx.AsyncClient | None = None,
) -> CollectedReview:
    """Fetch one explicitly allowed public upstream issue without credentials or attachments."""
    if (allowed_repositories is None or repository not in allowed_repositories
            or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or type(number) is not int or not 1 <= number <= 10**7):
        raise ReviewSourceError("INVALID_ISSUE_ID")
    if len(access_basis.strip()) < 10:
        raise ReviewSourceError("SOURCE_ACCESS_NOT_DOCUMENTED")
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10, follow_redirects=False)
    permalink = f"https://github.com/{repository}/issues/{number}"
    try:
        async with client.stream(
            "GET", f"{GITHUB_API}/repos/{repository}/issues/{number}",
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            timeout=10, follow_redirects=False,
        ) as response:
            if response.status_code in {404, 410}:
                raise ReviewSourceError("SOURCE_UNAVAILABLE")
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                body.extend(chunk)
                if len(body) > 65536:
                    raise ReviewSourceError("SOURCE_TOO_LARGE")
        issue = json.loads(body)
        if (
            not isinstance(issue, dict) or type(issue.get("number")) is not int
            or issue["number"] != number or issue.get("html_url") != permalink
            or "pull_request" in issue or not isinstance(issue.get("body"), str)
            or not isinstance(issue.get("created_at"), str)
        ):
            raise ReviewSourceError("INVALID_SOURCE_RECORD")
        text = normalize_text(issue["body"])
        if not text or len(text) > 20000:
            raise ReviewSourceError("INVALID_SOURCE_RECORD")
        return CollectedReview(
            platform="github_issue", external_id=f"{repository}#{number}",
            source_url=permalink, published_at=datetime.fromisoformat(issue["created_at"]),
            retrieved_at=datetime.now(UTC), software_context=software_context,
            selection_context=selection_context, collection_method="api", access_basis=access_basis,
            source_text=text,
        )
    except ReviewSourceError:
        raise
    except Exception:
        raise ReviewSourceError("SOURCE_READ_FAILED") from None
    finally:
        if owns_client:
            await client.aclose()
