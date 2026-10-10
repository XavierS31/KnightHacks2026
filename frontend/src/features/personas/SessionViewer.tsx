import { useEffect, useState } from 'react'
import type { components } from '../../shared/api-types'
import { request, type Persona, type Session } from '../../shared/api'

type StreamEvent = components['schemas']['StreamEvent']

export default function SessionViewer({ persona, sessionId, viewerToken }: {
  persona: Persona; sessionId: string; viewerToken: string
}) {
  const [session, setSession] = useState<Session | null>(null)
  const [connection, setConnection] = useState('Connecting')
  const [lastSeen, setLastSeen] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const [stale, setStale] = useState(false)
  useEffect(() => {
    let active = true
    let socket: WebSocket | null = null
    let lastSequence = -1
    let lastEventAt = Date.now()
    setSession(null); setError(null); setLastSeen(null); setStale(false); setConnection('Connecting')
    request<Session>(`/sessions/${sessionId}`, {
      headers: viewerToken ? { Authorization: `Bearer ${viewerToken}` } : {},
    }).then(result => {
      if (!active) return
      setSession(result)
      const url = new URL(`/api/v1/sessions/${sessionId}/stream`, window.location.href)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      socket = new WebSocket(url)
      socket.onopen = () => { socket?.send(JSON.stringify({ token: viewerToken })); setConnection('Awaiting session state') }
      socket.onmessage = ({ data }) => {
        if (!active) return
        try {
          const event: StreamEvent = JSON.parse(data)
          if (event.session_id !== sessionId || !Number.isInteger(event.sequence) || event.sequence <= lastSequence) return
          if (!['fixture', 'replay', 'live'].includes(event.mode)) return
          lastSequence = event.sequence; lastEventAt = Date.now()
          setLastSeen(lastEventAt); setStale(false); setConnection(`${event.mode} stream connected`)
          // Only session state is available now. No synthetic screenshot is presented.
          if (event.type === 'state' && event.payload.session) setSession(event.payload.session as Session)
        } catch { setError('Invalid stream event received.'); socket?.close() }
      }
      socket.onerror = () => { if (active) setError('Stream unavailable. Check the viewer token and API connection.') }
      socket.onclose = () => { if (active) setConnection('Disconnected') }
    }).catch((failure: Error) => { if (active) { setError(failure.message); setConnection('Unavailable') } })
    const timer = window.setInterval(() => { if (active) setStale(Date.now() - lastEventAt > 25000) }, 5000)
    return () => { active = false; window.clearInterval(timer); if (socket) { socket.onopen = null; socket.close() } }
  }, [sessionId, viewerToken, revision])
  return <article className="panel persona-viewer">
    <div className="section-heading"><h2>{persona.synthetic_name}</h2><span className="badge">{session?.stream_mode ?? 'unavailable'}</span></div>
    <p className="muted" role="status">{connection}{stale ? ' · stale connection' : ''}{lastSeen ? ` · last event ${new Date(lastSeen).toLocaleTimeString()}` : ''}</p>
    {error && <p role="alert">{error}</p>}
    <button onClick={() => setRevision(value => value + 1)}>Reconnect selected session</button>
    <dl className="persona-facts">
      <dt>Role / location</dt><dd>{persona.scenario.active_role} / {persona.scenario.location_id}</dd>
      <dt>Scenario</dt><dd>{persona.scenario.activity}</dd>
      <dt>Goal</dt><dd>{persona.scenario.goal}</dd>
      <dt>Constraints</dt><dd>{persona.constraints.join(', ')}</dd>
      <dt>Provenance</dt><dd>{Object.entries(persona.attribute_provenance).map(([key, value]) => `${key}: ${value}`).join(' · ')}</dd>
      <dt>Session ID</dt><dd className="persona-id">{sessionId}</dd>
      <dt>Outcome</dt><dd>{session?.outcome ?? 'Loading'}</dd>
    </dl>
    <h3>Software behavior · {persona.software_behavior.status.replace('_', ' ')}</h3>
    <p className="muted">{persona.software_behavior.limitations.join(' · ')}</p>
    <ul>{persona.software_behavior.patterns.map(pattern => <li key={pattern.id}>
      <strong>{pattern.tendency}</strong> ({pattern.dimension})
      <p>When: {pattern.trigger}. Trial policy: {pattern.agent_policy}</p>
      <p className="muted">Interpretation confidence: {pattern.interpretation_confidence}. {pattern.rationale}</p>
      <ul>{pattern.evidence_ids.map(id => {
        const evidence = persona.software_behavior.evidence.find(item => item.id === id)
        return <li key={id}>{evidence
          ? <>{evidence.source_url ? <a href={evidence.source_url} target="_blank" rel="noreferrer">{evidence.platform} review</a> : 'Illustrative fixture'}: {evidence.summary} ({evidence.report_type})</>
          : 'Review reference unavailable'}</li>
      })}</ul>
    </li>)}</ul>
    <div className="persona-no-frame"><strong>Browser frames unavailable</strong><p>This fixture has no browser execution or captured screenshots. The room's laptop props are illustrative.</p></div>
    <h3>Action timeline</h3>
    {session?.actions.length ? <ol>{session.actions.map(action => <li key={action.id}>{action.sequence}. {action.kind}: {action.result}</li>)}</ol> : <p className="muted">No executed actions have been recorded.</p>}
    <h3>Feedback</h3><p className="muted">{session?.feedback?.reason ?? 'No trial feedback has been recorded.'}</p>
  </article>
}
