"""Bounded source intake and immutable in-memory review snapshots, not population storage."""
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

import httpx
from pydantic import AwareDatetime, Field, HttpUrl, model_validator

from backend.app.shared.contracts import Contract, SoftwareReviewEvidence

HN_API = "https://hacker-news.firebaseio.com/v0"


class ReviewSourceError(Exception):
    """Only fixed safe codes reach logs/callers."""


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.suppressed = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.suppressed += 1
        elif tag in {"p", "br", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.suppressed = max(0, self.suppressed - 1)
        elif tag in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def normalize_html(text: str) -> str:
    parser = _PlainText()
    parser.feed(text)
    return normalize_text("".join(parser.parts))


class CollectedReview(Contract):
    platform: Literal["hacker_news", "reddit", "github_issue", "app_store", "review_site",
                      "forum", "other"]
    external_id: str = Field(min_length=1, max_length=200)
    source_url: HttpUrl
    published_at: AwareDatetime | None
    retrieved_at: AwareDatetime
    software_context: str = Field(min_length=1, max_length=300)
    selection_context: str = Field(min_length=1, max_length=1000)
    collection_method: Literal["api", "manual", "permitted_export"]
    access_basis: str = Field(min_length=10, max_length=1000)
    source_text: str = Field(min_length=1, max_length=20000, repr=False)

    @model_validator(mode="after")
    def validate_source(self):
        if not normalize_text(self.source_text):
            raise ValueError("Empty review text")
        if self.published_at is not None and self.published_at > self.retrieved_at:
            raise ValueError("Publication follows retrieval")
        if self.source_url.username or self.source_url.password:
            raise ValueError("Source URL cannot contain credentials")
        if self.platform == "hacker_news":
            expected = f"https://news.ycombinator.com/item?id={self.external_id}"
            if not self.external_id.isdecimal() or str(self.source_url) != expected:
                raise ValueError("Hacker News identity must match its canonical permalink")
        return self


async def collect_hn_item(item_id: int, *, software_context: str, selection_context: str,
                          access_basis: str, client: httpx.AsyncClient | None = None) -> CollectedReview:
    """Fetch one explicitly selected item. No search, tree traversal or author/vote retention."""
    if type(item_id) is not int or not 1 <= item_id <= 10**12:
        raise ReviewSourceError("INVALID_ITEM_ID")
    if len(access_basis.strip()) < 10:
        raise ReviewSourceError("SOURCE_ACCESS_NOT_DOCUMENTED")
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=10, follow_redirects=False)
    try:
        # Streaming caps bytes even when a server returns an unexpectedly large response.
        async with client.stream("GET", f"{HN_API}/item/{item_id}.json", timeout=10,
                                 follow_redirects=False) as response:
            response.raise_for_status()
            data = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                data.extend(chunk)
                if len(data) > 65536:
                    raise ReviewSourceError("SOURCE_TOO_LARGE")
        item = json.loads(data)
        if item is None or (isinstance(item, dict) and (item.get("deleted") or item.get("dead"))):
            raise ReviewSourceError("SOURCE_UNAVAILABLE")
        if (not isinstance(item, dict) or type(item.get("id")) is not int
                or item["id"] != item_id or item.get("type") not in {"comment", "story"}
                or not isinstance(item.get("text"), str)
                or type(item.get("time")) is not int):
            raise ReviewSourceError("INVALID_SOURCE_RECORD")
        text = normalize_html(item["text"])
        return CollectedReview(
            platform="hacker_news", external_id=str(item_id),
            source_url=f"https://news.ycombinator.com/item?id={item_id}",
            published_at=datetime.fromtimestamp(item["time"], UTC), retrieved_at=datetime.now(UTC),
            software_context=software_context, selection_context=selection_context,
            collection_method="api", access_basis=access_basis, source_text=text,
        )
    except ReviewSourceError:
        raise
    except Exception:
        raise ReviewSourceError("SOURCE_READ_FAILED") from None
    finally:
        if owns_client:
            await client.aclose()


class CuratedReview(Contract):
    evidence: SoftwareReviewEvidence
    approved_excerpt: str = Field(min_length=1, max_length=1200, repr=False)
    privacy_reviewed: Literal[True]
    access_basis: str = Field(min_length=10, max_length=1000)


def curate_review(source: CollectedReview, *, summary: str, excerpt: str,
                   report_type: Literal["self_report", "opinion"], privacy_reviewed: bool,
                   limitations: list[str]) -> CuratedReview:
    """Explicit manual support/privacy review; do not blindly approve a retrieved item."""
    source = CollectedReview.model_validate(source.model_dump())
    text = normalize_text(source.source_text)
    excerpt = normalize_text(excerpt)
    if not excerpt or excerpt not in text:
        raise ReviewSourceError("EXCERPT_NOT_IN_SOURCE")
    if not privacy_reviewed:
        raise ReviewSourceError("PRIVACY_REVIEW_REQUIRED")
    # Catch common accidental leaks; manual privacy review must also remove names/sensitive details.
    sensitive = r"hf_[A-Za-z0-9]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?i:bearer)\s+\S+|@[\w-]+"
    if re.search(sensitive, " ".join([excerpt, summary, source.software_context, *limitations])):
        raise ReviewSourceError("SENSITIVE_MODEL_CONTEXT")
    return CuratedReview(
        evidence=SoftwareReviewEvidence(
            id=uuid5(NAMESPACE_URL, f"repofusion:review:{source.platform}:{source.external_id}"),
            kind="source", platform=source.platform, external_id=source.external_id,
            source_url=source.source_url, published_at=source.published_at,
            retrieved_at=source.retrieved_at, software_context=source.software_context,
            summary=summary, report_type=report_type, collection_method=source.collection_method,
            content_sha256=hashlib.sha256(text.encode()).hexdigest(),
            selection_context=source.selection_context, extraction_version="manual-curation-v1",
            limitations=limitations,
        ), approved_excerpt=excerpt, privacy_reviewed=True, access_basis=source.access_basis,
    )


@dataclass(frozen=True)
class FrozenCorpus:
    """Canonical JSON is immutable; consumers receive detached Pydantic copies."""
    snapshot_json: str
    version: str

    def data(self):
        if hashlib.sha256(self.snapshot_json.encode()).hexdigest() != self.version:
            raise ReviewSourceError("CORPUS_VERSION_MISMATCH")
        return json.loads(self.snapshot_json)

    def reviews(self) -> list[CuratedReview]:
        return [CuratedReview.model_validate(r) for r in self.data()["reviews"]]


def freeze_corpus(reviews: list[CuratedReview], *, software_context: str,
                   selection_limits: list[str]) -> FrozenCorpus:
    if not 1 <= len(reviews) <= 100 or not selection_limits:
        raise ReviewSourceError("CORPUS_REQUIRES_BOUNDED_REVIEWS_AND_LIMITATIONS")
    validated = [CuratedReview.model_validate(r.model_dump()) for r in reviews]
    evidence = [r.evidence for r in validated]
    if any(e.kind != "source" or e.software_context != software_context for e in evidence):
        raise ReviewSourceError("CORPUS_SOURCE_CONTEXT_MISMATCH")
    for keys in ([e.id for e in evidence], [(e.platform, e.external_id) for e in evidence],
                 [str(e.source_url) for e in evidence], [e.content_sha256 for e in evidence]):
        if len(set(keys)) != len(keys):
            raise ReviewSourceError("DUPLICATE_CORPUS_SOURCE")
    snapshot = {"normalization_version": "nfkc-whitespace-v1", "software_context": software_context,
                "selection_limits": selection_limits,
                "reviews": [r.model_dump(mode="json") for r in sorted(validated,
                            key=lambda r: str(r.evidence.id))]}
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return FrozenCorpus(encoded, hashlib.sha256(encoded.encode()).hexdigest())
