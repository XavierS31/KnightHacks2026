import test from 'node:test'
import assert from 'node:assert/strict'
import { parseFrame, preservesActions, timestamp, validAction, validEvent, validSession } from './streamValidation.ts'

const now = Date.parse('2026-10-10T14:00:00Z')
const time = '2026-10-10T13:59:55Z'
const action = { id: 'action-1', session_id: 'session-1', sequence: 1, timestamp: time, kind: 'click', result: 'clicked' }
const session = { id: 'session-1', persona_id: 'persona-1', experiment_id: 'experiment', product_version_id: 'version', status: 'fixture', stream_mode: 'fixture', outcome: 'not_run', actions: [action] }
const event = { session_id: 'session-1', sequence: 1, timestamp: time, mode: 'fixture', type: 'heartbeat', payload: {} }
// Tiny PNG fixture tests transport validation, never supplies app frames or execution evidence.
const png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII='
const frame = { session_id: 'session-1', frame_sequence: 1, captured_at: time, mime_type: 'image/png', image_base64: png, width: 1, height: 1 }

test('timestamps require explicit timezone, valid date, and bounded future', () => {
  assert.equal(timestamp(time, now), now - 5000)
  for (const invalid of ['2026-10-10T14:00:00', 'invalid', '2026-10-10T14:01:00Z', '2026-02-30T12:00:00Z', '2026-10-10T24:00:00Z', 1]) assert.equal(timestamp(invalid, now), null)
})
test('state snapshots preserve accepted action history independent of key ordering', () => {
  assert.ok(preservesActions(session, { ...session, actions: [{ result: action.result, ...action }, { ...action, id: 'action-2', sequence: 2 }] }))
  assert.equal(preservesActions(session, { ...session, actions: [] }), false)
  assert.equal(preservesActions(session, { ...session, actions: [{ ...action, result: 'rewritten' }] }), false)
})
test('events reject foreign identity, reordered sequence, time regression and malformed payload', () => {
  assert.ok(validEvent(event, 'session-1', 0, now - 6000, now))
  for (const patch of [{ session_id: 'other' }, { sequence: 0 }, { sequence: 1.5 }, { timestamp: '2026-10-10T13:50:00Z' }, { mode: 'unknown' }, { type: 'unknown' }, { payload: [] }]) {
    assert.equal(validEvent({ ...event, ...patch }, 'session-1', 0, now - 6000, now), false)
  }
})
test('session requires selected persona and same-session monotonic actions', () => {
  assert.ok(validSession(session, 'session-1', 'persona-1', now))
  assert.equal(validSession(session, 'session-1', 'other', now), false)
  for (const patch of [{ id: 'other' }, { stream_mode: 'live' }, { actions: [{ ...action, session_id: 'other' }] }, { actions: [action, { ...action, id: 'action-2' }] }, { actions: [action, { ...action, id: 'action-2', sequence: 2, timestamp: '2026-10-10T13:50:00Z' }] }]) {
    assert.equal(validSession({ ...session, ...patch }, 'session-1', 'persona-1', now), false)
  }
  assert.equal(validAction({ ...action, sequence: -1 }, 'session-1', now), false)
})
test('feedback cannot reference another persona, session or absent action', () => {
  const feedback = { id: 'feedback', persona_id: 'persona-1', session_id: 'session-1', synthetic: true, reason: 'observed result', decision: 'stop', initial_relevance: 'low', post_trial_relevance: 'low', evidence_action_ids: ['action-1'], barriers: [], useful_parts: [], suggested_changes: [] }
  assert.ok(validSession({ ...session, feedback }, 'session-1', 'persona-1', now))
  for (const patch of [{ persona_id: 'other' }, { session_id: 'other' }, { synthetic: false }, { evidence_action_ids: ['missing'] }]) {
    assert.equal(validSession({ ...session, feedback: { ...feedback, ...patch } }, 'session-1', 'persona-1', now), false)
  }
})
test('frames accept bounded inline PNG and reject remote, corrupt, foreign, oversized or backward captures', () => {
  const accepted = parseFrame(frame, 'session-1', null, now)
  assert.equal(accepted.source, `data:image/png;base64,${png}`)
  assert.equal(parseFrame(frame, 'session-1', accepted, now), null)
  for (const patch of [{ session_id: 'other' }, { mime_type: 'image/svg+xml' }, { image_base64: 'https://example.com/frame?token=secret' }, { image_base64: btoa('not a PNG') }, { image_base64: 'A'.repeat(3 * 1024 * 1024) }, { width: 0 }, { captured_at: '2026-10-10T14:01:00Z' }, { captured_at: '2026-10-10T13:00:00Z', frame_sequence: 2 }]) {
    assert.equal(parseFrame({ ...frame, ...patch }, 'session-1', accepted, now), null)
  }
})
