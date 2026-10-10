"""B's evidence sink for C's session repository and local exact-frame artifacts."""

import asyncio
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Awaitable, Callable
from uuid import UUID

from backend.app.features.personas.session_execution import TrialGateError
from backend.app.shared.contracts import Action, Session, StreamEvent
from backend.app.shared.session_records import SessionRepository, validate_artifact_ref


class DurableEvidenceSink:
    """A single live attempt. The experiment and product version must already exist."""

    durable = True

    def __init__(self, repository: SessionRepository, *, task_id: UUID, attempt: int,
                 artifact_root: Path, before_write: Callable[[], Awaitable[None]] | None = None,
                 provenance: dict | None = None):
        if attempt < 1:
            raise ValueError("Attempt must be positive")
        self.repository = repository
        self.task_id = task_id
        self.attempt = attempt
        self.artifact_root = artifact_root
        self.before_write = before_write
        self.provenance = dict(provenance or {})
        self.session_id: UUID | None = None
        self.finished: Session | None = None
        self._feedback_written = False

    async def _guard(self):
        if self.before_write is not None:
            await self.before_write()

    async def save_session(self, session: Session):
        if session.stream_mode != "live" or session.status == "fixture":
            raise TrialGateError("LIVE_EVIDENCE_REQUIRED")
        await self._guard()
        if self.session_id is None:
            if session.status != "running" or session.outcome != "not_run":
                raise TrialGateError("LIVE_SESSION_MUST_START_RUNNING")
            await asyncio.to_thread(self.repository.create, session, task_id=self.task_id,
                                    attempt=self.attempt,
                                    provenance={"stream_mode": "live", "stop_reason": None,
                                                **self.provenance})
            self.session_id = session.id
            return
        if session.id != self.session_id:
            raise TrialGateError("EVIDENCE_SESSION_MISMATCH")
        if self.finished is not None:
            if session != self.finished:
                raise TrialGateError("TERMINAL_SESSION_CHANGED")
            return
        if session.status == "running":
            return
        if session.status not in {"completed", "failed", "cancelled"}:
            raise TrialGateError("INVALID_LIVE_SESSION_STATE")
        if session.feedback is not None and not self._feedback_written:
            await asyncio.to_thread(self.repository.record_feedback, session.feedback)
            self._feedback_written = True
        await asyncio.to_thread(self.repository.finish, session.id, status=session.status,
                                outcome=session.outcome, stop_reason=session.stop_reason)
        self.finished = session.model_copy(deep=True)

    async def save_action(self, action: Action):
        if self.session_id is None or action.session_id != self.session_id or self.finished is not None:
            raise TrialGateError("EVIDENCE_ACTION_SESSION_MISMATCH")
        await self._guard()
        await asyncio.to_thread(self.repository.append_action, action)

    async def save_frame(self, event: StreamEvent) -> str:
        if (self.session_id is None or event.session_id != self.session_id
                or event.mode != "live" or self.finished is not None):
            raise TrialGateError("EVIDENCE_FRAME_SESSION_MISMATCH")
        await self._guard()
        return await asyncio.to_thread(self._write_frame, event)

    def _write_frame(self, event: StreamEvent) -> str:
        payload = event.payload
        if (payload.get("session_id") != str(event.session_id)
                or payload.get("mime_type") != "image/png"
                or not isinstance(payload.get("frame_sequence"), int)
                or payload["frame_sequence"] < 1):
            raise TrialGateError("INVALID_CAPTURED_FRAME")
        try:
            png = base64.b64decode(payload["image_base64"], validate=True)
        except (KeyError, ValueError, binascii.Error):
            raise TrialGateError("INVALID_CAPTURED_FRAME") from None
        if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) > 2 * 1024 * 1024:
            raise TrialGateError("INVALID_CAPTURED_FRAME")
        relative = PurePosixPath("sessions", str(event.session_id), "frames",
                                 f"{payload['frame_sequence']:03d}.png")
        reference = str(relative)
        validate_artifact_ref(reference)
        path = self.artifact_root.joinpath(*relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as stream:
                stream.write(png)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if path.read_bytes() != png:
                raise TrialGateError("CAPTURED_FRAME_CONFLICT") from None
        metadata = {"session_id": str(event.session_id), "sequence": event.sequence,
                    "frame_sequence": payload["frame_sequence"],
                    "captured_at": payload.get("captured_at"),
                    "sha256": hashlib.sha256(png).hexdigest()}
        sidecar = path.with_suffix(".json")
        encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
        try:
            with sidecar.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            if sidecar.read_text(encoding="utf-8") != encoded:
                raise TrialGateError("CAPTURED_FRAME_CONFLICT") from None
        return reference
