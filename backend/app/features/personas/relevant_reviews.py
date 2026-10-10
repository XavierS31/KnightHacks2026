"""Bounded public upstream issue intake; source bodies stay transient and untrusted."""

import json
from datetime import UTC, datetime

import httpx

from .review_corpus import (
    CollectedReview,
    FrozenCorpus,
    ReviewSourceError,
    curate_review,
    freeze_corpus,
    normalize_text,
)

PUBLIC_REPOSITORIES = frozenset({"jsvine/pdfplumber", "frictionlessdata/frictionless-py"})
GITHUB_API = "https://api.github.com"
SOURCETABLE_CONTEXT = (
    "SourceTable: local PDF table extraction, inspection of source cells, "
    "and typed tabular schema validation/error recovery."
)
ACCESS_BASIS = (
    "Public, unauthenticated fixed issue GET documented at "
    "https://docs.github.com/en/rest/issues/issues#get-an-issue; GitHub API terms and "
    "privacy reviewed 2026-10-10 at https://docs.github.com/en/site-policy/github-terms/"
    "github-terms-of-service and https://docs.github.com/en/site-policy/privacy-policies/"
    "github-general-privacy-statement. No training, author retention or bulk redistribution; "
    "retain factual paraphrases, hashes, permalinks and <=25-word support excerpts only. "
    "Public access does not imply a blanket content license."
)

# Purposefully selected support snippets, not a population sample or source mirror.
# Fetch-time substring checks reject edited/deleted sources instead of inventing support.
SELECTED_ISSUES = (
    ("jsvine/pdfplumber", 311,
     "After debug, I found some non-existed lines/edges get identified. This cause table has wrong size.",
     "A reporter compared detected boundaries with the PDF and investigated unexpected table shape.",
     "Source comparison and diagnostic inspection after extraction shape mismatch."),
    ("jsvine/pdfplumber", 140,
     "Additionally, when I crop out the blank columns, the extraction works fine",
     "A reporter inspected a table extraction and compared results after excluding empty outer columns.",
     "Visual inspection and checking extracted content against the original PDF."),
    ("frictionlessdata/frictionless-py", 809,
     "I have a CSV file and a JSON Table Schema and I want to validate the CSV file against the schema.",
     "A reporter requested a small example showing how to validate tabular data against a schema.",
     "Onboarding through a concise worked schema-validation example."),
    ("frictionlessdata/frictionless-py", 766,
     "code to reproduce error, the validation step should throw errors and doesn't seem to",
     "A reporter tested declared string constraints and integer values, expecting visible row errors.",
     "Checking that typed validation surfaces errors rather than assuming success."),
    ("frictionlessdata/frictionless-py", 1633,
     "I was expected an invalid report specifying a `missing-primary-key` for example",
     "A reporter wanted an invalid report identifying the missing field instead of an unexpected exception.",
     "Preference for explicit field-level validation feedback; primary-key controls are out of scope."),
)


async def collect_sourcetable_corpus() -> FrozenCorpus:
    """Collect the five curated upstream reports; fail the snapshot if any support is unavailable."""
    reviews = []
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
        for repository, number, excerpt, summary, rationale in SELECTED_ISSUES:
            if len(excerpt.split()) > 25:
                raise ReviewSourceError("SUPPORT_EXCERPT_TOO_LONG")
            source = await collect_public_issue(
                repository, number, software_context=SOURCETABLE_CONTEXT,
                selection_context=(
                    "Purposeful 2026-10-10 selection from upstream PDF extraction/schema-validation "
                    f"issue reports, not SourceTable users or a date-bounded representative sample. {rationale}"
                ), access_basis=ACCESS_BASIS, client=client,
            )
            reviews.append(curate_review(
                source, summary=summary, excerpt=excerpt, report_type="self_report",
                privacy_reviewed=True, limitations=[
                    "One self-report about an upstream tool; attachments/comments were not collected or tested.",
                    "Not evidence of a SourceTable defect, demographic distribution or behavior prevalence.",
                    "Transfer only abstract preferences compatible with observed SourceTable controls.",
                    "Versions and input documents differ from SourceTable; no reproduction is claimed.",
                ],
            ))
    return freeze_corpus(
        reviews, software_context=SOURCETABLE_CONTEXT, selection_limits=[
            "Five purposefully selected public GitHub issue bodies from two upstream projects; no random sampling.",
            "Developer issue reports overrepresent troubleshooting; no SourceTable users, author attributes or votes.",
            "Source inspection and typed validation are related workflows; crop/primary-key controls are unavailable.",
            "Dates vary; no frequency, consensus, demand, representativeness or current reproducibility is inferred.",
            "Only short privacy-curated excerpts, factual paraphrases and metadata are retained; source bodies are transient.",
        ],
    )


async def collect_public_issue(
    repository: str, number: int, *, software_context: str, selection_context: str,
    access_basis: str, client: httpx.AsyncClient | None = None,
) -> CollectedReview:
    """Fetch one selected issue from two public upstreams, without credentials or attachments."""
    if repository not in PUBLIC_REPOSITORIES or type(number) is not int or not 1 <= number <= 10**7:
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
