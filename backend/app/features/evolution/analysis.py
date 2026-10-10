"""Group supplied fixture feedback without inventing evidence or calling inference."""

from collections import defaultdict
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.app.features.evolution.evidence import validate_session_evidence
from backend.app.features.evolution.models import PRIORITY_FORMULA, AnalysisReport, FeedbackCluster
from backend.app.shared.contracts import Feedback, Session


def analyze_fixture_sessions(experiment_id: UUID, sessions: list[Session]) -> AnalysisReport:
    evidence = validate_session_evidence(experiment_id, sessions, "fixture")
    groups: dict[tuple[str, str], list[Feedback]] = defaultdict(list)

    for feedback in evidence.feedback:
        outcome = evidence.sessions[feedback.session_id].outcome
        if outcome == "infrastructure_failure":
            category = "infrastructure"
        elif outcome == "irrelevant":
            category = "relevance"
        else:
            category = "product"
        issues = {" ".join(barrier.split()) for barrier in feedback.barriers if barrier.strip()}
        if not issues and feedback.post_trial_relevance == "low":
            category = "relevance"
            issues = {feedback.reason.strip()} if feedback.reason.strip() else set()
        for issue in issues:
            groups[(category, issue.casefold())].append(feedback)

    feedback_present = len(evidence.feedback)
    clusters = []
    for (category, normalized_issue), members in groups.items():
        refs = sorted({action_id for member in members
                       for action_id in member.evidence_action_ids}, key=str)
        affected_share = len(members) / feedback_present
        # Explicit kickoff heuristics, not model severity predictions or observed human impact.
        severity = 3 if category == "product" else 2
        effort = 1.0
        strength = 1.0  # All accepted members have same-session action references.
        clusters.append(FeedbackCluster(
            id=uuid5(NAMESPACE_URL, f"repofusion:{experiment_id}:{category}:{normalized_issue}"),
            category=category,
            issue=normalized_issue,
            supporting_session_ids=sorted({member.session_id for member in members}, key=str),
            supporting_feedback_ids=sorted({member.id for member in members}, key=str),
            evidence_action_ids=refs,
            severity=severity,
            severity_source="kickoff_default",
            affected_share=affected_share,
            evidence_strength=strength,
            estimated_effort_hours=effort,
            effort_source="kickoff_default",
            priority_score=round(severity * affected_share * strength / effort, 6),
            patch_eligible=category == "product",
        ))
    clusters.sort(key=lambda cluster: (-cluster.priority_score, cluster.category, cluster.issue))
    return AnalysisReport(
        experiment_id=experiment_id,
        mode="fixture",
        method="deterministic_evidence_grouping",
        inference_used=False,
        sessions_seen=len(sessions),
        feedback_present=feedback_present,
        denominator=feedback_present,
        priority_formula=PRIORITY_FORMULA,
        clusters=clusters,
        unclustered_feedback_ids=[],
        proposals=[],
        role_runs=[],
        limitations=[
            "Fixture-only grouping; no browser execution, Hugging Face inference or Neon write occurred.",
            "Scores use kickoff defaults: severity 3 for product, 2 otherwise; effort 1 hour.",
            "Evidence strength measures reference presence, not causal proof or feedback quality.",
            "Denominator is supplied sessions with feedback, not the 500-person population.",
        ],
        next_gate="Collect real persisted feedback, then run structured HF role analysis.",
    )
