"""Run the structured analyst, prioritizer and UX roles on validated live session evidence.

Models only propose. Deterministic checks here reject unknown, duplicate or cross-session
references, keep product/infrastructure/relevance findings separate, and compute affected
share, evidence strength and the priority score themselves.
"""

from dataclasses import dataclass
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from backend.app.features.evolution.evidence import EvidenceIndex, validate_session_evidence
from backend.app.features.evolution.models import (
    PRIORITY_FORMULA,
    AnalysisReport,
    FeedbackCluster,
    ProposalDraft,
    RoleRun,
)
from backend.app.features.evolution.roles import (
    ANALYST_PROMPT_VERSION,
    PRIORITIZER_PROMPT_VERSION,
    UX_PROMPT_VERSION,
    AnalystOutput,
    PrioritizerOutput,
    UxOutput,
    analyst_messages,
    prioritizer_messages,
    ux_messages,
)
from backend.app.shared.contracts import Action, Feedback, Session
from backend.app.shared.inference import HuggingFaceInference, InferenceResult

# One analyst call holds every feedback item; larger populations need batching first (P3).
MAX_ANALYSIS_FEEDBACK = 30
ALL_CATEGORIES = frozenset({"product", "infrastructure", "relevance"})


class AnalysisInputTooLarge(ValueError):
    """The evidence exceeds what one bounded analyst request may hold."""


class RoleOutputRejected(ValueError):
    """A role output referenced evidence it may not use; nothing from the run is kept."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class Labels:
    feedback: dict[str, Feedback]
    actions: dict[str, Action]

    @classmethod
    def build(cls, evidence: EvidenceIndex) -> "Labels":
        feedback = {f"F{index}": item for index, item in enumerate(evidence.feedback, start=1)}
        actions = {}
        for item in evidence.feedback:
            for action in sorted(evidence.sessions[item.session_id].actions,
                                 key=lambda action: action.sequence):
                actions[f"A{len(actions) + 1}"] = action
        return cls(feedback=feedback, actions=actions)

    def action_ref(self, identity: UUID) -> str:
        return next(ref for ref, action in self.actions.items() if action.id == identity)


@dataclass(frozen=True)
class ClusterDraft:
    ref: str
    id: UUID
    category: str
    issue: str
    members: list[Feedback]
    actions: list[Action]
    affected_share: float
    evidence_strength: float
    patch_eligible: bool
    rationale: str


def allowed_categories(feedback: Feedback, session: Session) -> frozenset[str]:
    """Session outcomes the model may not reclassify across the product boundary."""
    if session.outcome == "infrastructure_failure":
        return frozenset({"infrastructure"})
    if session.outcome == "irrelevant":
        return frozenset({"relevance"})
    if feedback.post_trial_relevance == "low" and not any(item.strip() for item in feedback.barriers):
        return frozenset({"relevance"})
    return ALL_CATEGORIES


def _unique(refs: list[str], kind: str) -> None:
    if len(set(refs)) != len(refs):
        raise RoleOutputRejected("DUPLICATE_REFERENCE", f"A role output repeated a {kind} reference.")


def _resolve(refs: list[str], known: dict[str, Any], kind: str) -> list[Any]:
    _unique(refs, kind)
    if not set(refs) <= known.keys():
        raise RoleOutputRejected("UNKNOWN_REFERENCE", f"A role output cited an unknown {kind}.")
    return [known[ref] for ref in refs]


def _run(role: str, result: InferenceResult) -> RoleRun:
    provenance = result.provenance
    return RoleRun(role=role, **{name: provenance[name] for name in (
        "request_id", "model_id", "provider", "prompt_version", "configuration_hash",
        "latency_ms", "retry_count")})


def check_findings(experiment_id: UUID, output: AnalystOutput, labels: Labels,
                   evidence: EvidenceIndex) -> list[ClusterDraft]:
    drafts: list[ClusterDraft] = []
    seen_issues: set[tuple[str, str]] = set()
    for finding in output.findings:
        issue = " ".join(finding.issue.split())
        key = (finding.category, issue.casefold())
        if not issue or key in seen_issues:
            raise RoleOutputRejected("DUPLICATE_FINDING", "The analyst repeated or blanked a finding.")
        seen_issues.add(key)
        members = _resolve(finding.feedback_refs, labels.feedback, "feedback")
        for member in members:
            if finding.category not in allowed_categories(member, evidence.sessions[member.session_id]):
                raise RoleOutputRejected(
                    "CATEGORY_MISMATCH",
                    "The analyst moved feedback across the product, infrastructure and relevance "
                    "boundary that its session outcome sets.")
        member_sessions = {member.session_id for member in members}
        actions = _resolve(finding.action_refs, labels.actions, "action")
        if any(action.session_id not in member_sessions for action in actions):
            raise RoleOutputRejected(
                "CROSS_SESSION_REFERENCE",
                "The analyst cited an action from a session outside the finding's feedback.")
        cited_sessions = {action.session_id for action in actions}
        strength = len(cited_sessions) / len(member_sessions)
        drafts.append(ClusterDraft(
            ref=f"C{len(drafts) + 1}",
            id=uuid5(NAMESPACE_URL, f"repofusion:{experiment_id}:{key[0]}:{key[1]}"),
            category=finding.category, issue=issue, members=members, actions=actions,
            affected_share=len(members) / len(evidence.feedback), evidence_strength=strength,
            # A product defect without action evidence for every member cannot reach a proposal.
            patch_eligible=finding.category == "product" and strength == 1,
            rationale=finding.rationale,
        ))
    return drafts


def prioritize(drafts: list[ClusterDraft], output: PrioritizerOutput) -> list[FeedbackCluster]:
    by_ref = {draft.ref: draft for draft in drafts}
    assessments = {item.cluster_ref: item for item in output.assessments}
    _resolve([item.cluster_ref for item in output.assessments], by_ref, "cluster")
    if assessments.keys() != by_ref.keys():
        raise RoleOutputRejected("INCOMPLETE_ASSESSMENT",
                                 "The prioritizer must assess every cluster exactly once.")
    clusters = []
    for ref, draft in by_ref.items():
        assessment = assessments[ref]
        clusters.append(FeedbackCluster(
            id=draft.id, category=draft.category, issue=draft.issue,
            supporting_session_ids=sorted({member.session_id for member in draft.members}, key=str),
            supporting_feedback_ids=sorted({member.id for member in draft.members}, key=str),
            evidence_action_ids=sorted({action.id for action in draft.actions}, key=str),
            severity=assessment.severity, severity_source="prioritizer_role",
            affected_share=draft.affected_share, evidence_strength=draft.evidence_strength,
            estimated_effort_hours=assessment.estimated_effort_hours,
            effort_source="prioritizer_role",
            priority_score=round(assessment.severity * draft.affected_share
                                 * draft.evidence_strength / assessment.estimated_effort_hours, 6),
            patch_eligible=draft.patch_eligible,
            analyst_rationale=draft.rationale, priority_rationale=assessment.rationale,
        ))
    return clusters


def check_proposals(drafts: list[ClusterDraft], output: UxOutput,
                    labels: Labels) -> list[ProposalDraft]:
    by_ref = {draft.ref: draft for draft in drafts}
    _resolve([item.cluster_ref for item in output.proposals], by_ref, "cluster")
    proposals = []
    for item in output.proposals:
        draft = by_ref[item.cluster_ref]
        if not draft.patch_eligible:
            raise RoleOutputRejected(
                "INELIGIBLE_PROPOSAL",
                "The UX reviewer proposed a change for a cluster that is not an evidenced product defect.")
        actions = _resolve(item.action_refs, labels.actions, "action")
        if not {action.id for action in actions} <= {action.id for action in draft.actions}:
            raise RoleOutputRejected("EVIDENCE_OUTSIDE_CLUSTER",
                                     "The UX reviewer cited an action outside its cluster's evidence.")
        proposals.append(ProposalDraft(
            id=uuid5(NAMESPACE_URL, f"repofusion:proposal:{draft.id}"), cluster_id=draft.id,
            title=item.title, problem=item.problem, change=item.change,
            acceptance_check=item.acceptance_check,
            supporting_session_ids=sorted({action.session_id for action in actions}, key=str),
            evidence_action_ids=sorted({action.id for action in actions}, key=str),
            supported=bool(actions),
            support_note=(f"Cites {len(actions)} action(s) from the cluster's own sessions."
                          if actions else "No cited action evidence; not a supported proposal."),
        ))
    return proposals


def _analyst_data(labels: Labels, evidence: EvidenceIndex) -> dict[str, Any]:
    feedback_refs = {item.id: ref for ref, item in labels.feedback.items()}
    return {
        "feedback": [{
            "ref": ref, "session_outcome": evidence.sessions[item.session_id].outcome,
            "initial_relevance": item.initial_relevance,
            "post_trial_relevance": item.post_trial_relevance, "decision": item.decision,
            "useful_parts": item.useful_parts, "barriers": item.barriers,
            "suggested_changes": item.suggested_changes, "reason": item.reason,
            "cited_actions": [labels.action_ref(identity) for identity in item.evidence_action_ids],
        } for ref, item in labels.feedback.items()],
        "actions": [{
            "ref": ref,
            "feedback_ref": feedback_refs[evidence.sessions[action.session_id].feedback.id],
            "sequence": action.sequence, "kind": action.kind, "target": action.target,
            "result": action.result,
        } for ref, action in labels.actions.items()],
    }


def _prioritizer_data(drafts: list[ClusterDraft]) -> dict[str, Any]:
    return {"clusters": [{
        "ref": draft.ref, "category": draft.category, "issue": draft.issue,
        "supporting_sessions": len(draft.members), "affected_share": round(draft.affected_share, 4),
        "evidence_strength": round(draft.evidence_strength, 4),
        "barriers": sorted({barrier for member in draft.members for barrier in member.barriers}),
    } for draft in drafts]}


def _ux_data(drafts: list[ClusterDraft], labels: Labels) -> dict[str, Any]:
    return {"clusters": [{
        "ref": draft.ref, "issue": draft.issue,
        "barriers": sorted({barrier for member in draft.members for barrier in member.barriers}),
        "suggested_changes": sorted({change for member in draft.members
                                     for change in member.suggested_changes}),
        "evidence": [{"ref": labels.action_ref(action.id), "kind": action.kind,
                      "target": action.target, "result": action.result} for action in draft.actions],
    } for draft in drafts]}


async def analyze_with_roles(experiment_id: UUID, sessions: list[Session],
                             inference: HuggingFaceInference) -> AnalysisReport:
    evidence = validate_session_evidence(experiment_id, sessions, "live")
    if len(evidence.feedback) > MAX_ANALYSIS_FEEDBACK:
        raise AnalysisInputTooLarge(
            f"Live analysis holds at most {MAX_ANALYSIS_FEEDBACK} feedback items per request.")
    labels = Labels.build(evidence)
    context = {"experiment_id": str(experiment_id)}
    runs: list[RoleRun] = []
    clusters: list[FeedbackCluster] = []
    proposals: list[ProposalDraft] = []
    clustered: set[UUID] = set()

    if evidence.feedback:
        analyst = await inference.generate_structured(
            role="analyst", messages=analyst_messages(_analyst_data(labels, evidence)),
            output_schema=AnalystOutput, prompt_version=ANALYST_PROMPT_VERSION,
            request_context=context)
        runs.append(_run("analyst", analyst))
        drafts = check_findings(experiment_id, analyst.value, labels, evidence)
        clustered = {member.id for draft in drafts for member in draft.members}
        if drafts:
            prioritizer = await inference.generate_structured(
                role="prioritizer", messages=prioritizer_messages(_prioritizer_data(drafts)),
                output_schema=PrioritizerOutput, prompt_version=PRIORITIZER_PROMPT_VERSION,
                request_context=context)
            runs.append(_run("prioritizer", prioritizer))
            clusters = prioritize(drafts, prioritizer.value)
        eligible = [draft for draft in drafts if draft.patch_eligible]
        if eligible:
            reviewer = await inference.generate_structured(
                role="ux_reviewer", messages=ux_messages(_ux_data(eligible, labels)),
                output_schema=UxOutput, prompt_version=UX_PROMPT_VERSION, request_context=context)
            runs.append(_run("ux_reviewer", reviewer))
            proposals = check_proposals(drafts, reviewer.value, labels)

    clusters.sort(key=lambda cluster: (-cluster.priority_score, cluster.category, cluster.issue))
    return AnalysisReport(
        experiment_id=experiment_id, mode="live", method="structured_hf_roles",
        inference_used=bool(runs), sessions_seen=len(sessions),
        feedback_present=len(evidence.feedback), denominator=len(evidence.feedback),
        priority_formula=PRIORITY_FORMULA, clusters=clusters,
        unclustered_feedback_ids=[item.id for item in evidence.feedback if item.id not in clustered],
        proposals=proposals, role_runs=runs,
        limitations=[
            "Feedback is synthetic persona feedback, not observed human behavior.",
            "Role outputs are model proposals checked by deterministic reference rules, not human review.",
            "Severity and effort are prioritizer estimates; affected share and evidence strength are "
            "computed from cited records.",
            "Denominator is persisted sessions with feedback for this experiment.",
            "Role provenance is returned in this report; the live API persists the checked report "
            "before returning proposals.",
        ],
        next_gate="Human review of supported proposals before the improvement lifecycle.",
    )
