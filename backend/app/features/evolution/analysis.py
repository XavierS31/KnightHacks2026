"""Group supplied fixture feedback without inventing evidence or calling inference."""

from collections import defaultdict
from pathlib import PurePosixPath, PureWindowsPath
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.app.features.evolution.models import AnalysisReport, FeedbackCluster
from backend.app.shared.contracts import Session


class EvidenceMismatch(ValueError):
    """The submitted feedback cannot be grounded in its own session."""


def validate_patch_paths(paths: list[str]) -> None:
    """Limit future product patches to relative product/ descendants."""
    if not paths:
        raise ValueError("A non-empty approved product path list is required.")
    for raw in paths:
        normalized = raw.replace("\\", "/")
        path = PurePosixPath(normalized)
        windows_path = PureWindowsPath(raw)
        if (path.is_absolute() or windows_path.drive or ".." in path.parts
                or not path.parts or path.parts[0] != "product" or len(path.parts) < 2):
            raise ValueError("Patch paths must stay within relative product/ descendants.")


def analyze_fixture_sessions(experiment_id: UUID, sessions: list[Session]) -> AnalysisReport:
    session_ids: set[UUID] = set()
    action_ids: set[UUID] = set()
    feedback_ids: set[UUID] = set()
    groups: dict[tuple[str, str], list[Session]] = defaultdict(list)
    feedback_present = 0

    for session in sessions:
        if session.status != "fixture" or session.stream_mode != "fixture":
            raise EvidenceMismatch("This offline analysis accepts explicitly fixture sessions only.")
        if session.experiment_id != experiment_id or session.id in session_ids:
            raise EvidenceMismatch("Sessions must be unique and belong to the requested experiment.")
        session_ids.add(session.id)
        own_actions: set[UUID] = set()
        own_sequences: set[int] = set()
        for action in session.actions:
            if (action.session_id != session.id or action.id in action_ids
                    or action.sequence in own_sequences):
                raise EvidenceMismatch("Action identities and sequences must be unique to their session.")
            own_actions.add(action.id)
            action_ids.add(action.id)
            own_sequences.add(action.sequence)

        feedback = session.feedback
        if feedback is None:
            continue
        if (feedback.session_id != session.id or feedback.persona_id != session.persona_id
                or feedback.id in feedback_ids):
            raise EvidenceMismatch("Feedback identity must match its persona and session.")
        feedback_ids.add(feedback.id)
        referenced = set(feedback.evidence_action_ids)
        if not referenced or not referenced <= own_actions:
            raise EvidenceMismatch("Feedback needs existing action references from its own session.")
        feedback_present += 1

        if session.outcome == "infrastructure_failure":
            category = "infrastructure"
        elif session.outcome == "irrelevant":
            category = "relevance"
        else:
            category = "product"
        issues = {" ".join(barrier.split()) for barrier in feedback.barriers if barrier.strip()}
        if not issues and feedback.post_trial_relevance == "low":
            category = "relevance"
            issues = {feedback.reason.strip()} if feedback.reason.strip() else set()
        for issue in issues:
            groups[(category, issue.casefold())].append(session)

    clusters = []
    for (category, normalized_issue), members in groups.items():
        refs = sorted({action_id for member in members
                       for action_id in member.feedback.evidence_action_ids}, key=str)
        affected_share = len(members) / feedback_present
        # Explicit kickoff heuristics, not model severity predictions or observed human impact.
        severity = 3 if category == "product" else 2
        effort = 1.0
        strength = 1.0  # All accepted members have same-session action references.
        clusters.append(FeedbackCluster(
            id=uuid5(NAMESPACE_URL, f"repofusion:{experiment_id}:{category}:{normalized_issue}"),
            category=category,
            issue=normalized_issue,
            supporting_session_ids=sorted({member.id for member in members}, key=str),
            evidence_action_ids=refs,
            severity=severity,
            affected_share=affected_share,
            evidence_strength=strength,
            estimated_effort_hours=effort,
            priority_score=round(severity * affected_share * strength / effort, 6),
            patch_eligible=category == "product",
        ))
    clusters.sort(key=lambda cluster: (-cluster.priority_score, cluster.category, cluster.issue))
    return AnalysisReport(
        experiment_id=experiment_id,
        sessions_seen=len(sessions),
        feedback_present=feedback_present,
        denominator=feedback_present,
        clusters=clusters,
        limitations=[
            "Fixture-only grouping; no browser execution, Hugging Face inference or Neon write occurred.",
            "Scores use kickoff defaults: severity 3 for product, 2 otherwise; effort 1 hour.",
            "Evidence strength measures reference presence, not causal proof or feedback quality.",
            "Denominator is supplied sessions with feedback, not the 500-person population.",
        ],
        next_gate="Collect real persisted feedback, then run structured HF role analysis.",
    )
