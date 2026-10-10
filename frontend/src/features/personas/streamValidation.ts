import type { components } from '../../shared/api-types'

type Session = components['schemas']['Session']
type Action = components['schemas']['Action']
type StreamEvent = components['schemas']['StreamEvent']
const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const positive = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) > 0
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === 'string')
const oneOf = (value: unknown, choices: string[]) => typeof value === 'string' && choices.includes(value)

export function timestamp(value: unknown, now = Date.now()): number | null {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) return null
  const year = Number(value.slice(0, 4)), month = Number(value.slice(5, 7)), day = Number(value.slice(8, 10))
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate()
  if (month < 1 || month > 12 || day < 1 || day > days || Number(value.slice(11, 13)) > 23
    || Number(value.slice(14, 16)) > 59 || Number(value.slice(17, 19)) > 59) return null
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) && parsed <= now + 30000 ? parsed : null
}

export function preservesActions(previous: Session, next: Session): boolean {
  return next.actions.length >= previous.actions.length && previous.actions.every((action, index) => {
    const incoming = next.actions[index]
    return action.id === incoming.id && action.session_id === incoming.session_id && action.sequence === incoming.sequence
      && action.timestamp === incoming.timestamp && action.kind === incoming.kind && action.result === incoming.result
      && (action.target ?? null) === (incoming.target ?? null) && (action.artifact_ref ?? null) === (incoming.artifact_ref ?? null)
  })
}

export function validAction(value: unknown, sessionId: string, now = Date.now()): value is Action {
  return record(value) && typeof value.id === 'string' && value.id.length > 0 && value.session_id === sessionId
    && positive(value.sequence) && timestamp(value.timestamp, now) !== null
    && oneOf(value.kind, ['click', 'type', 'select', 'scroll', 'navigate', 'stop', 'check'])
    && typeof value.result === 'string' && (value.target == null || typeof value.target === 'string')
    && (value.artifact_ref == null || typeof value.artifact_ref === 'string')
}

export function validSession(value: unknown, sessionId: string, personaId: string, now = Date.now()): value is Session {
  if (!record(value) || value.id !== sessionId || value.persona_id !== personaId
    || typeof value.experiment_id !== 'string' || typeof value.product_version_id !== 'string'
    || !oneOf(value.status, ['fixture', 'queued', 'running', 'completed', 'failed', 'cancelled'])
    || !oneOf(value.outcome, ['not_run', 'success', 'application_failure', 'infrastructure_failure', 'irrelevant'])
    || !oneOf(value.stream_mode, ['unavailable', 'fixture', 'live', 'replay'])
    || (value.status === 'fixture' && !['fixture', 'unavailable'].includes(String(value.stream_mode)))
    || (value.stop_reason != null && typeof value.stop_reason !== 'string') || !Array.isArray(value.actions)) return false
  let sequence = 0, time = -Infinity
  const ids = new Set<string>()
  for (const action of value.actions) {
    if (!validAction(action, sessionId, now) || action.sequence <= sequence || ids.has(action.id) || timestamp(action.timestamp, now)! < time) return false
    sequence = action.sequence; time = timestamp(action.timestamp, now)!; ids.add(action.id)
  }
  if (value.feedback != null) {
    const feedback = value.feedback
    if (!record(feedback) || feedback.session_id !== sessionId || feedback.persona_id !== personaId
      || typeof feedback.id !== 'string' || feedback.synthetic !== true || typeof feedback.reason !== 'string'
      || !oneOf(feedback.decision, ['stop', 'continue'])
      || !oneOf(feedback.initial_relevance, ['low', 'medium', 'high']) || !oneOf(feedback.post_trial_relevance, ['low', 'medium', 'high'])
      || !strings(feedback.evidence_action_ids) || !feedback.evidence_action_ids.every(id => ids.has(id))
      || !strings(feedback.barriers) || !strings(feedback.useful_parts) || !strings(feedback.suggested_changes)) return false
  }
  return true
}

export type CapturedFrame = { sequence: number; capturedAt: string; capturedMs: number; source: string }

export function parseFrame(value: unknown, sessionId: string, previous: CapturedFrame | null, now = Date.now()): CapturedFrame | null {
  if (!record(value) || value.session_id !== sessionId || !positive(value.frame_sequence)
    || value.mime_type !== 'image/png' || typeof value.image_base64 !== 'string') return null
  const captured = timestamp(value.captured_at, now)
  if (captured === null || (previous && (value.frame_sequence <= previous.sequence || captured < previous.capturedMs))) return null
  // Only bounded inline PNGs; never fetch model-provided URLs or token-bearing references.
  const encoded = value.image_base64
  if (!encoded.length || encoded.length > Math.ceil(2 * 1024 * 1024 / 3) * 4
    || encoded.length % 4 !== 0 || !/^[A-Za-z0-9+/]+={0,2}$/.test(encoded)) return null
  let bytes: string
  try { bytes = atob(encoded) } catch { return null }
  if (bytes.length > 2 * 1024 * 1024 || bytes.length < 33
    || ![137, 80, 78, 71, 13, 10, 26, 10].every((byte, index) => bytes.charCodeAt(index) === byte)
    || bytes.slice(12, 16) !== 'IHDR') return null
  const uint32 = (offset: number) => ((bytes.charCodeAt(offset) * 2 ** 24) + (bytes.charCodeAt(offset + 1) << 16) + (bytes.charCodeAt(offset + 2) << 8) + bytes.charCodeAt(offset + 3))
  const width = uint32(16), height = uint32(20)
  if (uint32(8) !== 13 || !positive(width) || !positive(height) || width > 8192 || height > 8192 || width * height > 32 * 1024 * 1024
    || (value.width != null && value.width !== width) || (value.height != null && value.height !== height)) return null
  return { sequence: value.frame_sequence, capturedAt: String(value.captured_at), capturedMs: captured, source: `data:image/png;base64,${encoded}` }
}

export function validEvent(value: unknown, sessionId: string, sequence: number, previousTime: number, now = Date.now()): value is StreamEvent {
  return record(value) && value.session_id === sessionId && Number.isSafeInteger(value.sequence) && Number(value.sequence) >= 0
    && Number(value.sequence) > sequence && oneOf(value.mode, ['fixture', 'live', 'replay'])
    && oneOf(value.type, ['state', 'action', 'frame', 'heartbeat', 'error']) && record(value.payload)
    && timestamp(value.timestamp, now) !== null && timestamp(value.timestamp, now)! >= previousTime
}
