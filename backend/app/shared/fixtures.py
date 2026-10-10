from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from .contracts import (
    Capability,
    Evidence,
    Experiment,
    ExperimentCounts,
    Improvement,
    Persona,
    ProductVersion,
    Proposal,
    Repository,
    Scenario,
    Session,
    SoftwareBehaviorPattern,
    SoftwareBehaviorProfile,
    SoftwareReviewEvidence,
)


def fixture_id(key: str):
    return uuid5(NAMESPACE_URL, f"repofusion:fixture:{key}")


FIXTURE_TIME = datetime(2026, 10, 10, tzinfo=UTC)
EVIDENCE = Evidence(
    source="scaffold fixture", reference="backend/app/shared/fixtures.py",
    collected_at=FIXTURE_TIME, kind="fixture",
    note="Illustrative only; no repository was discovered or executed.",
)
REPOSITORIES = [
    Repository(id=fixture_id(f"repo-{i}"), full_name=name, url="https://example.com/fixture",
               discovery_mode="fixture", stars=0, description=description, evidence=[EVIDENCE])
    for i, name, description in [
        (1, "fixture/document-parser", "Illustrative structured document extraction"),
        (2, "fixture/study-cards", "Illustrative study-card composition"),
    ]
]
CAPABILITY = Capability(
    id=fixture_id("capability"), key="compose_study_cards", description="Illustrative combined flow",
    input_schema={"type": "object"}, output_schema={"type": "object"},
    validated=False, evidence=[EVIDENCE],
)
PROPOSAL = Proposal(
    id=fixture_id("proposal"), title="Documents into study cards",
    repository_ids=[r.id for r in REPOSITORIES], audience="Students preparing for an exam",
    problem="Turn notes into review material", adapter_boundary="Structured sections → card inputs",
    novelty="unresolved", feasibility="unreviewed", status="fixture", evidence=[EVIDENCE],
)
VERSION = ProductVersion(
    id=fixture_id("version-v1"), label="v1 fixture", status="fixture",
    briefing="An illustrative study workflow. No source integration has been validated.",
    capabilities=[CAPABILITY], limitations=["Fixture only", "No executed usability results"],
)
PERSONAS = []
REVIEW_FIXTURE = SoftwareReviewEvidence(
    id=fixture_id("software-review"), kind="fixture", platform="fixture",
    external_id="illustrative-review-01", source_url=None, published_at=None,
    retrieved_at=FIXTURE_TIME, software_context="Illustrative document-to-study-card workflow",
    summary="Illustration: a user wants to try a sample before committing their own documents.",
    report_type="fixture", collection_method="fixture", content_sha256=None,
    selection_context="Handwritten scaffold example; no reviews were collected.",
    extraction_version="fixture-v1", limitations=["Invented illustration, not a real person's review"],
)
BEHAVIOR_FIXTURE = SoftwareBehaviorProfile(
    status="fixture", corpus_id=fixture_id("review-corpus"), corpus_version="fixture-v1",
    generation_version="fixture-v1", evidence=[REVIEW_FIXTURE],
    patterns=[SoftwareBehaviorPattern(
        id=fixture_id("behavior-sample-first"), dimension="onboarding",
        tendency="Try a sample before uploading personal documents",
        trigger="First use of a document workflow",
        agent_policy="Prefer an available sample input within the mandatory trial action budget.",
        evidence_ids=[REVIEW_FIXTURE.id], interpretation_confidence="low",
        rationale="Illustrates the required evidence-to-behavior link; not extracted from real reviews.",
    )], limitations=["Fixture only; real review collection and behavior extraction remain unimplemented"],
)
for i in range(10):
    persona_id = fixture_id(f"persona-{i}")
    cohort = ["undergraduate", "graduate", "faculty", "staff", "resident"][i % 5]
    location = ["library", "classroom", "home", "office"][i % 4]
    PERSONAS.append(Persona(
        id=persona_id, synthetic_name=f"Synthetic persona {i + 1:02d}", cohort=cohort,
        roles=[cohort], skills=["Web navigation"], goals=["Explore a relevant sample"],
        constraints=["Bounded trial"],
        attribute_provenance={"name": "fictional_detail", "role": "scenario_assumption"},
        software_behavior=BEHAVIOR_FIXTURE,
        scenario=Scenario(id=fixture_id(f"scenario-{i}"), persona_id=persona_id,
                          active_role=cohort, location_id=location, activity="Sample review",
                          goal="Evaluate whether a sample workflow is useful", device="laptop",
                          time_budget_minutes=2, assumptions=["Fictional role, schedule and location"]),
    ))
EXPERIMENT = Experiment(
    id=fixture_id("experiment"), population_id=fixture_id("population"),
    product_version_id=VERSION.id, status="fixture",
    counts=ExperimentCounts(configured=10, queued=0, running=0, completed=0, failed=0),
    inference_profile={"mode": "fixture", "model": None},
)
SESSIONS = [Session(
    id=fixture_id(f"session-{i}"), experiment_id=EXPERIMENT.id, persona_id=p.id,
    product_version_id=VERSION.id, status="fixture", outcome="not_run", actions=[],
    stream_mode="fixture",
) for i, p in enumerate(PERSONAS)]
IMPROVEMENT = Improvement(
    id=fixture_id("improvement"), title="Example: clarify the input format",
    issue="Illustrative suggestion, not observed feedback", supporting_session_ids=[],
    severity=2, affected_share=0, evidence_strength=0, estimated_effort_hours=1,
    acceptance_check="A supported-input hint is visible", allowed_paths=["product/"], status="fixture",
)
