"""Validate that feedback is grounded in its own session before any grouping or inference."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from backend.app.shared.contracts import Action, Feedback, Session

FINISHED_STATUSES = {"completed", "failed", "cancelled"}


class EvidenceMismatch(ValueError):
    """The submitted or stored feedback cannot be grounded in its own session."""


@dataclass(frozen=True)
class EvidenceIndex:
    sessions: dict[UUID, Session]
    actions: dict[UUID, Action]
    feedback: list[Feedback]


def validate_session_evidence(
    experiment_id: UUID, sessions: list[Session], mode: Literal["fixture", "live"],
) -> EvidenceIndex:
    """Reject foreign, duplicate or cross-session references; fixture and live never mix."""
    by_session: dict[UUID, Session] = {}
    actions: dict[UUID, Action] = {}
    feedback_ids: set[UUID] = set()
    feedback: list[Feedback] = []

    for session in sessions:
        is_fixture = session.status == "fixture" or session.stream_mode == "fixture"
        if mode == "fixture" and not (session.status == "fixture" and session.stream_mode == "fixture"):
            raise EvidenceMismatch("This offline analysis accepts explicitly fixture sessions only.")
        if mode == "live" and is_fixture:
            raise EvidenceMismatch("Live analysis cannot use fixture sessions as evidence.")
        if session.experiment_id != experiment_id or session.id in by_session:
            raise EvidenceMismatch("Sessions must be unique and belong to the requested experiment.")
        by_session[session.id] = session
        own_actions: set[UUID] = set()
        own_sequences: set[int] = set()
        for action in session.actions:
            if (action.session_id != session.id or action.id in actions
                    or action.sequence in own_sequences):
                raise EvidenceMismatch("Action identities and sequences must be unique to their session.")
            own_actions.add(action.id)
            own_sequences.add(action.sequence)
            actions[action.id] = action

        item = session.feedback
        if item is None:
            continue
        if mode == "live" and session.status not in FINISHED_STATUSES:
            raise EvidenceMismatch("Feedback must belong to a finished session.")
        if (item.session_id != session.id or item.persona_id != session.persona_id
                or item.id in feedback_ids):
            raise EvidenceMismatch("Feedback identity must match its persona and session.")
        referenced = set(item.evidence_action_ids)
        if not referenced or not referenced <= own_actions:
            raise EvidenceMismatch("Feedback needs existing action references from its own session.")
        feedback_ids.add(item.id)
        feedback.append(item)

    return EvidenceIndex(sessions=by_session, actions=actions, feedback=feedback)
