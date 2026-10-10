"""Invented unit-test source records; these never establish live review collection."""
import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import HttpUrl, ValidationError

from backend.app.features.personas.behavior_extraction import (
    BehaviorProposals,
    extract_behavior_draft,
    validate_proposals,
)
from backend.app.features.personas.review_corpus import (
    CollectedReview,
    FrozenCorpus,
    ReviewSourceError,
    collect_hn_item,
    curate_review,
    freeze_corpus,
    normalize_html,
)
from backend.app.shared.fixtures import REVIEW_FIXTURE
from backend.app.shared.inference import HuggingFaceInference, InferenceError
from backend.app.shared.settings import Settings


def source(item_id="101", text="I prefer to try a sample before uploading my notes."):
    return CollectedReview(
        platform="hacker_news", external_id=item_id,
        source_url=f"https://news.ycombinator.com/item?id={item_id}",
        published_at=datetime(2020, 1, 1, tzinfo=UTC),
        retrieved_at=datetime(2026, 10, 10, tzinfo=UTC),
        software_context="Study-card software", selection_context="Test-only chosen item",
        collection_method="manual", access_basis="Invented unit-test record, not live retrieval",
        source_text=text,
    )


def curated(item_id="101", text="I prefer to try a sample before uploading my notes."):
    return curate_review(source(item_id, text), summary="Test paraphrase: prefers trying a sample.",
                          excerpt=text, report_type="self_report", privacy_reviewed=True,
                          limitations=["Invented test data, no real review collected"])


def corpus():
    return freeze_corpus([curated()], software_context="Study-card software",
                          selection_limits=["Test data; not representative"])


def proposals(snapshot):
    evidence_id = str(snapshot.reviews()[0].evidence.id)
    return BehaviorProposals.model_validate({
        "software_context": "Study-card software", "limitations": ["Tentative single report"],
        "proposals": [{"pattern": {
            "id": str(uuid4()), "dimension": "onboarding", "tendency": "Try a sample first",
            "trigger": "First use", "agent_policy": "Choose an available sample within trial bounds",
            "evidence_ids": [evidence_id], "interpretation_confidence": "low",
            "rationale": "Test report expresses preference for a sample",
        }, "source_support": [{"evidence_id": evidence_id, "excerpt": "try a sample"}]}],
    })


def test_normalize_html_and_source_hash_not_summary_hash():
    assert normalize_html("<p> A&nbsp; B </p><script>bad</script><p>C</p>") == "A B C"
    review = curated()
    assert review.evidence.content_sha256 == hashlib.sha256(source().source_text.encode()).hexdigest()
    assert review.evidence.content_sha256 != hashlib.sha256(review.evidence.summary.encode()).hexdigest()
    assert "source_text" not in str(review.model_dump())


@pytest.mark.parametrize("changed", ["duplicate_id", "copied_content", "fixture", "context"])
def test_corpus_rejects_duplicate_fixture_or_incompatible_sources(changed):
    first = curated()
    second = curated("102", "I use keyboard navigation.")
    if changed == "duplicate_id":
        second.evidence.id = first.evidence.id
    elif changed == "copied_content":
        second = curated("102")
    elif changed == "fixture":
        second.evidence = REVIEW_FIXTURE.model_copy(deep=True)
    else:
        second.evidence.software_context = "Unrelated software"
    with pytest.raises(ReviewSourceError):
        freeze_corpus([first, second], software_context="Study-card software", selection_limits=["Bias"])


def test_snapshot_is_order_independent_and_detached_from_mutable_inputs():
    first, second = curated(), curated("102", "I use keyboard navigation.")
    frozen = freeze_corpus([first, second], software_context="Study-card software", selection_limits=["Bias"])
    reverse = freeze_corpus([second, first], software_context="Study-card software", selection_limits=["Bias"])
    assert frozen.version == reverse.version
    before = frozen.snapshot_json
    first.evidence.summary = "Changed"
    detached = frozen.reviews()
    detached[0].evidence.summary = "Changed again"
    assert frozen.snapshot_json == before
    assert all(r.evidence.summary not in {"Changed", "Changed again"} for r in frozen.reviews())
    with pytest.raises(ReviewSourceError, match="CORPUS_VERSION_MISMATCH"):
        FrozenCorpus(frozen.snapshot_json + " ", frozen.version).data()


@pytest.mark.parametrize("excerpt,privacy,code", [
    ("Not in original", True, "EXCERPT_NOT_IN_SOURCE"),
    ("try a sample", False, "PRIVACY_REVIEW_REQUIRED"),
    ("hf_testsecret", True, "SENSITIVE_MODEL_CONTEXT"),
])
def test_curation_requires_literal_support_and_privacy_review(excerpt, privacy, code):
    record = source(text=source().source_text + " hf_testsecret")
    with pytest.raises(ReviewSourceError, match=code):
        curate_review(record, summary="A sample preference", excerpt=excerpt,
                       report_type="self_report", privacy_reviewed=privacy, limitations=["Test"])


def test_canonical_source_identity_and_aware_dates():
    data = source().model_dump(mode="json")
    data["source_url"] = "https://news.ycombinator.com/item?id=999"
    with pytest.raises(ValidationError):
        CollectedReview.model_validate(data)
    data = source().model_dump(mode="json")
    data["retrieved_at"] = "2026-10-10T00:00:00"
    with pytest.raises(ValidationError):
        CollectedReview.model_validate(data)


async def test_hn_adapter_fixed_endpoint_drops_authors_votes_and_html():
    requests = []

    def handle(request):
        requests.append(str(request.url))
        return httpx.Response(200, json={"id": 101, "type": "comment", "time": 1577836800,
                                         "by": "private-author", "score": 999,
                                         "text": "<p>I try samples.</p>"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await collect_hn_item(101, software_context="Study-card software",
                                       selection_context="Test chosen item", access_basis="Test API access",
                                       client=client)
    assert requests == ["https://hacker-news.firebaseio.com/v0/item/101.json"]
    assert result.source_text == "I try samples."
    assert "private-author" not in str(result.model_dump())
    assert "score" not in result.model_dump()
    assert result.collection_method == "api"


@pytest.mark.parametrize("item,code", [
    (None, "SOURCE_UNAVAILABLE"), ({"id": 101, "deleted": True}, "SOURCE_UNAVAILABLE"),
    ({"id": 101, "dead": True}, "SOURCE_UNAVAILABLE"),
    ({"id": 102, "type": "comment", "time": 1, "text": "A"}, "INVALID_SOURCE_RECORD"),
    ({"id": 101, "type": "job", "time": 1, "text": "A"}, "INVALID_SOURCE_RECORD"),
    ({"id": 101, "type": "comment", "time": 1, "text": "A" * 70000}, "SOURCE_TOO_LARGE"),
])
async def test_hn_unavailable_and_malformed_records(item, code):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=json.dumps(item)))) as client:
        with pytest.raises(ReviewSourceError, match=code):
            await collect_hn_item(101, software_context="Study cards", selection_context="Test",
                                  access_basis="Test API access", client=client)


async def test_source_errors_are_sanitized():
    def handle(request):
        raise httpx.ConnectError("hf_secret", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ReviewSourceError) as failure:
            await collect_hn_item(101, software_context="Study cards", selection_context="Test",
                                  access_basis="Test API access", client=client)
    assert str(failure.value) == "SOURCE_READ_FAILED"


@pytest.mark.parametrize("change,code", [
    ("citation", "INVALID_EXTRACTION_CITATIONS"),
    ("quote", "UNSUPPORTED_SOURCE_EXCERPT"),
    ("context", "EXTRACTION_CONTEXT_MISMATCH"),
    ("duplicate", "DUPLICATE_BEHAVIOR_PATTERN"),
])
def test_unsupported_extractions_rejected(change, code):
    snapshot = corpus()
    output = proposals(snapshot)
    if change == "citation":
        output.proposals[0].pattern.evidence_ids = [uuid4()]
    elif change == "quote":
        output.proposals[0].source_support[0].excerpt = "Fabricated quotation"
    elif change == "context":
        output.software_context = "Unrelated"
    else:
        output.proposals.append(output.proposals[0])
    with pytest.raises(ReviewSourceError, match=code):
        validate_proposals(output, snapshot)


async def test_hf_extraction_remains_pending_with_frozen_lineage_and_minimal_context():
    snapshot = corpus()
    output = proposals(snapshot)

    class FakeHF:
        calls = []

        async def chat_completion(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content=output.model_dump_json()))], usage=None)

    client = FakeHF()
    adapter = HuggingFaceInference(Settings(_env_file=None, app_mode="live", hf_token="test-secret",
        hf_model_id="test/model", hf_provider="test-provider", experiment_budget_limit=1), client)
    result = await extract_behavior_draft(snapshot, adapter)
    assert result.corpus_version == snapshot.version
    assert result.status == "pending_independent_support_review"
    assert json.loads(result.provenance_json)["role"] == "software_behavior_extractor"
    sent = client.calls[0]["messages"][1]["content"]
    assert "source_text" not in sent and "source_url" not in sent and "test-secret" not in sent
    assert client.calls[0]["response_format"]["json_schema"]["strict"]
    assert not hasattr(result, "software_behavior")


async def test_fixture_mode_blocks_extraction_inference():
    adapter = HuggingFaceInference(Settings(_env_file=None, app_mode="fixture"))
    with pytest.raises(InferenceError, match="FIXTURE_INFERENCE_FORBIDDEN"):
        await extract_behavior_draft(corpus(), adapter)


@pytest.mark.parametrize("item_id", [0, -1, True, "101", 10**13])
async def test_invalid_source_ids_fail_before_network(item_id):
    called = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: called.append(request))) as client:
        with pytest.raises(ReviewSourceError, match="INVALID_ITEM_ID"):
            await collect_hn_item(item_id, software_context="Study cards", selection_context="Test",
                                  access_basis="Test API access", client=client)
    assert not called


def test_cross_posted_content_deduplicates_across_platforms():
    first, second = curated(), curated("102")
    second.evidence.platform = "forum"
    second.evidence.source_url = HttpUrl("https://example.com/test-only-copied-post")
    with pytest.raises(ReviewSourceError, match="DUPLICATE_CORPUS_SOURCE"):
        freeze_corpus([first, second], software_context="Study-card software", selection_limits=["Bias"])


async def test_oversized_model_context_never_calls_inference():
    reviews = [curated(str(101 + i), "Unique test text " + str(i) + ": " + "a" * 1100)
               for i in range(20)]
    snapshot = freeze_corpus(reviews, software_context="Study-card software", selection_limits=["Bias"])
    adapter = HuggingFaceInference(Settings(_env_file=None, app_mode="fixture"))
    with pytest.raises(ReviewSourceError, match="EXTRACTION_CONTEXT_TOO_LARGE"):
        await extract_behavior_draft(snapshot, adapter)


@pytest.mark.parametrize("reviews,limits", [([], ["Bias"]), ([curated()], [])])
def test_corpus_cannot_freeze_missing_sources_or_limits(reviews, limits):
    with pytest.raises(ReviewSourceError, match="CORPUS_REQUIRES_BOUNDED_REVIEWS_AND_LIMITATIONS"):
        freeze_corpus(reviews, software_context="Study-card software", selection_limits=limits)
