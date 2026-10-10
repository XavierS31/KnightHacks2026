"""Prevent unsourced behavior, broken review lineage and fixture promotion."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.main import app
from backend.app.shared.contracts import (
    Persona,
    PersonaSummary,
    SoftwareBehaviorProfile,
    SoftwareReviewEvidence,
)
from backend.app.shared.fixtures import BEHAVIOR_FIXTURE, PERSONAS, REVIEW_FIXTURE, fixture_id


def source_profile():
    # Invented test data, never a collected review or production fixture.
    data = BEHAVIOR_FIXTURE.model_dump(mode="json")
    data["status"] = "review_informed"
    data["evidence"][0].update(
        kind="source", platform="hacker_news", external_id="test-only-item",
        source_url="https://example.com/test-only-review", report_type="self_report",
        collection_method="manual", content_sha256="a" * 64,
    )
    return data


def test_persona_requires_software_behavior():
    data = PERSONAS[0].model_dump(mode="json")
    del data["software_behavior"]
    with pytest.raises(ValidationError, match="software_behavior"):
        Persona.model_validate(data)


@pytest.mark.parametrize("platform", ["reddit", "hacker_news", "github_issue", "app_store", "review_site", "forum", "other"])
def test_public_review_platforms_are_supported(platform):
    data = source_profile()
    data["evidence"][0]["platform"] = platform
    profile = SoftwareBehaviorProfile.model_validate(data)
    assert profile.patterns[0].evidence_ids == [profile.evidence[0].id]


@pytest.mark.parametrize("field,value", [
    ("source_url", None), ("content_sha256", None), ("content_sha256", "invalid"),
    ("report_type", "fixture"), ("collection_method", "fixture"), ("platform", "fixture"),
    ("retrieved_at", "2026-10-10T00:00:00"),
])
def test_source_reviews_require_valid_provenance(field, value):
    data = source_profile()["evidence"][0]
    data[field] = value
    with pytest.raises(ValidationError):
        SoftwareReviewEvidence.model_validate(data)


def test_publication_cannot_follow_retrieval():
    data = source_profile()["evidence"][0]
    data["published_at"] = "2026-10-11T00:00:00Z"
    with pytest.raises(ValidationError, match="publication"):
        SoftwareReviewEvidence.model_validate(data)


def test_fixture_cannot_claim_a_real_source_url():
    data = REVIEW_FIXTURE.model_dump(mode="json")
    data["source_url"] = "https://example.com/test-only-review"
    with pytest.raises(ValidationError, match="Fixture reviews"):
        SoftwareReviewEvidence.model_validate(data)


@pytest.mark.parametrize("missing", ["patterns", "evidence"])
def test_behavior_requires_patterns_and_reviews(missing):
    data = source_profile()
    data[missing] = []
    with pytest.raises(ValidationError):
        SoftwareBehaviorProfile.model_validate(data)


def test_pattern_cannot_cite_an_unknown_review():
    data = source_profile()
    data["patterns"][0]["evidence_ids"] = [str(fixture_id("unknown-review"))]
    with pytest.raises(ValidationError, match="reference reviews"):
        SoftwareBehaviorProfile.model_validate(data)


@pytest.mark.parametrize("duplicate", ["review_id", "external_id", "pattern_id", "pattern_reference"])
def test_duplicate_evidence_cannot_inflate_support(duplicate):
    data = source_profile()
    if duplicate in ("review_id", "external_id"):
        data["evidence"].append(deepcopy(data["evidence"][0]))
        if duplicate == "external_id":
            data["evidence"][1]["id"] = str(fixture_id("different-review-id"))
    elif duplicate == "pattern_id":
        data["patterns"].append(deepcopy(data["patterns"][0]))
    else:
        data["patterns"][0]["evidence_ids"] *= 2
    with pytest.raises(ValidationError):
        SoftwareBehaviorProfile.model_validate(data)


@pytest.mark.parametrize("direction", ["fixture_as_source", "source_as_fixture"])
def test_profile_cannot_mix_fixture_and_source_provenance(direction):
    data = source_profile() if direction == "source_as_fixture" else BEHAVIOR_FIXTURE.model_dump(mode="json")
    data["status"] = "fixture" if direction == "source_as_fixture" else "review_informed"
    with pytest.raises(ValidationError, match="status must match"):
        SoftwareBehaviorProfile.model_validate(data)


def test_live_summary_rejects_fixture_behavior():
    with pytest.raises(ValidationError, match="Live personas require"):
        PersonaSummary(mode="live", personas=PERSONAS, experiments=[], sessions=[], next_gate="Test")
    persona_data = PERSONAS[0].model_dump(mode="json")
    persona_data["software_behavior"] = source_profile()
    persona = Persona.model_validate(persona_data)
    summary = PersonaSummary(mode="live", personas=[persona], experiments=[], sessions=[], next_gate="Test")
    assert summary.personas[0].software_behavior.status == "review_informed"


def test_summary_exposes_honest_behavior_fixtures():
    response = TestClient(app).get("/api/v1/personas/summary")
    assert response.status_code == 200
    for persona in response.json()["personas"]:
        behavior = persona["software_behavior"]
        assert behavior["status"] == "fixture"
        assert behavior["evidence"][0]["source_url"] is None
        assert behavior["patterns"][0]["evidence_ids"] == [behavior["evidence"][0]["id"]]
