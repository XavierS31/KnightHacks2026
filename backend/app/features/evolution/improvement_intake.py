"""Bind E2 improvements to stored E1 proposals and their executed product evidence."""

from uuid import UUID

from backend.app.features.evolution.boundary import PATCHABLE_PATHS
from backend.app.features.evolution.evidence import validate_session_evidence
from backend.app.features.evolution.models import AnalysisReport
from backend.app.features.evolution.role_analysis import allowed_categories
from backend.app.shared.contracts import Improvement, Session
from backend.app.shared.database import RecordInvalid


def improvement_from_report(report: AnalysisReport, proposal_id: UUID, allowed_paths: list[str],
                            sessions: list[Session], base_version_id: UUID) -> Improvement:
    """A scope is proposed here; the lifecycle still requires human scope review and QA."""
    if report.mode != "live" or not report.inference_used:
        raise RecordInvalid("An improvement requires a live E1 analysis with recorded inference.")
    proposals = [item for item in report.proposals if item.id == proposal_id]
    if len(proposals) != 1 or not proposals[0].supported:
        raise RecordInvalid("The improvement must name one supported E1 proposal.")
    proposal = proposals[0]
    clusters = [item for item in report.clusters if item.id == proposal.cluster_id]
    if (len(clusters) != 1 or clusters[0].category != "product"
            or not clusters[0].patch_eligible or clusters[0].evidence_strength != 1):
        raise RecordInvalid("Only a fully evidenced product cluster can start an improvement.")
    cluster = clusters[0]
    if (not allowed_paths or len(set(allowed_paths)) != len(allowed_paths)
            or any(scope != "product/ui" and scope not in PATCHABLE_PATHS
                   for scope in allowed_paths)):
        raise RecordInvalid("The proposed scope must stay inside the three-file UI boundary.")
    evidence = validate_session_evidence(report.experiment_id, sessions, "live")
    session_ids = set(proposal.supporting_session_ids)
    action_ids = set(proposal.evidence_action_ids)
    if (not session_ids or not action_ids or len(session_ids) != len(proposal.supporting_session_ids)
            or len(action_ids) != len(proposal.evidence_action_ids)
            or not session_ids <= set(cluster.supporting_session_ids)
            or not action_ids <= set(cluster.evidence_action_ids)
            or not session_ids <= evidence.sessions.keys()
            or not action_ids <= evidence.actions.keys()):
        raise RecordInvalid("Proposal citations must resolve inside its product cluster.")
    if {evidence.actions[identity].session_id for identity in action_ids} != session_ids:
        raise RecordInvalid("Every supporting session needs its own cited action.")
    for identity in session_ids:
        session = evidence.sessions[identity]
        if (session.product_version_id != base_version_id or session.feedback is None
                or "product" not in allowed_categories(session.feedback, session)
                or session.outcome == "not_run" or not any(
                    barrier.strip() for barrier in session.feedback.barriers)):
            raise RecordInvalid("Proposal evidence must be executed product feedback on frozen v1.")
    return Improvement(
        id=proposal.id, title=proposal.title,
        issue=f"{proposal.problem}\nProposed change: {proposal.change}",
        supporting_session_ids=sorted(session_ids), severity=cluster.severity,
        affected_share=cluster.affected_share, evidence_strength=cluster.evidence_strength,
        estimated_effort_hours=cluster.estimated_effort_hours,
        acceptance_check=proposal.acceptance_check, allowed_paths=allowed_paths, status="proposed")


def validate_improvement(improvement: Improvement, report: AnalysisReport,
                         sessions: list[Session], base_version_id: UUID) -> None:
    expected = improvement_from_report(report, improvement.id, improvement.allowed_paths,
                                       sessions, base_version_id)
    # Citation order is immaterial, but duplicates and caller-edited evidence are rejected.
    submitted = improvement.model_copy(update={
        "supporting_session_ids": sorted(improvement.supporting_session_ids)})
    if submitted != expected:
        raise RecordInvalid("The improvement differs from its stored E1 proposal or priority inputs.")
