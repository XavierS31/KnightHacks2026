import { useEffect, useState } from 'react'
import { request, type Persona, type Session } from '../../shared/api'
import { parseFrame, preservesActions, timestamp, validAction, validEvent, validSession, type CapturedFrame } from './streamValidation'

export default function SessionViewer({ persona, sessionId, viewerToken }: {
  persona: Persona; sessionId: string; viewerToken: string
}) {
  const [session, setSession] = useState<Session | null>(null)
  const [connection, setConnection] = useState('Connecting')
  const [lastSeen, setLastSeen] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const [stale, setStale] = useState(false)
  const [frame, setFrame] = useState<CapturedFrame | null>(null)
  const [frameStale, setFrameStale] = useState(false)
  const [mode, setMode] = useState<Session['stream_mode']>('unavailable')
  useEffect(() => {
    let active = true
    let socket: WebSocket | null = null
    let lastSequence = -1
    let lastTimestamp = -Infinity
    let currentSession: Session | null = null
    let latestFrame: CapturedFrame | null = null
    let lastEventAt = Date.now()
    setSession(null); setError(null); setLastSeen(null); setStale(false); setFrame(null); setFrameStale(false); setMode('unavailable'); setConnection('Connecting')
    request<unknown>(`/sessions/${encodeURIComponent(sessionId)}`, {
      headers: viewerToken ? { Authorization: `Bearer ${viewerToken}` } : {},
    }).then(result => {
      if (!active) return
      if (!validSession(result, sessionId, persona.id)
        || (persona.software_behavior.status === 'fixture' && !['fixture', 'unavailable'].includes(result.stream_mode))) throw new Error('Selected session identity or state is invalid.')
      currentSession = result; setSession(result); setMode(result.stream_mode)
      const url = new URL(`/api/v1/sessions/${encodeURIComponent(sessionId)}/stream`, window.location.href)
      url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
      socket = new WebSocket(url)
      socket.onopen = () => { socket?.send(JSON.stringify({ token: viewerToken })); setConnection('Awaiting session state') }
      socket.onmessage = ({ data }) => {
        if (!active) return
        try {
          if (typeof data !== 'string' || data.length > 3 * 1024 * 1024) throw new Error('Invalid stream event')
          const event: unknown = JSON.parse(data)
          if (!validEvent(event, sessionId, lastSequence, lastTimestamp)) throw new Error('Invalid stream event')
          if ((persona.software_behavior.status === 'fixture' || currentSession?.status === 'fixture') && event.mode !== 'fixture') throw new Error('Invalid fixture mode')
          if (event.type === 'state') {
            const incoming = event.payload.session
            if (!validSession(incoming, sessionId, persona.id) || incoming.stream_mode !== event.mode
              || (currentSession && !preservesActions(currentSession, incoming))) throw new Error('Invalid session state')
            currentSession = incoming; setSession(incoming)
          } else if (event.type === 'action') {
            const action = event.payload.action
            const previous = currentSession?.actions.at(-1)
            if (!currentSession || !validAction(action, sessionId) || currentSession.actions.some(item => item.id === action.id)
              || (previous && (action.sequence <= previous.sequence || timestamp(action.timestamp)! < timestamp(previous.timestamp)!))) throw new Error('Invalid action')
            currentSession = { ...currentSession, actions: [...currentSession.actions, action] }; setSession(currentSession)
          } else if (event.type === 'frame') {
            const capturedFrame = parseFrame(event.payload, sessionId, latestFrame)
            if (!capturedFrame) throw new Error('Invalid frame')
            latestFrame = capturedFrame; setFrame(capturedFrame); setFrameStale(Date.now() - capturedFrame.capturedMs > 25000)
          } else if (event.type === 'error') {
            setError('The session stream reported a failure. Reconnect to inspect the selected session.')
          }
          lastSequence = event.sequence; lastTimestamp = timestamp(event.timestamp)!; lastEventAt = Date.now()
          setMode(event.mode)
          setLastSeen(lastEventAt); setStale(false); setConnection(`${event.mode} stream connected`)
        } catch { setError('Invalid stream event received.'); socket?.close() }
      }
      socket.onerror = () => { if (active) setError('Stream unavailable. Check the viewer token and API connection.') }
      socket.onclose = () => { if (active) setConnection('Disconnected') }
    }).catch(() => { if (active) { setError('Selected session unavailable or invalid. Check access and the API connection.'); setConnection('Unavailable') } })
    const timer = window.setInterval(() => { if (active) { setStale(Date.now() - lastEventAt > 25000); setFrameStale(!!latestFrame && Date.now() - latestFrame.capturedMs > 25000) } }, 5000)
    return () => { active = false; window.clearInterval(timer); if (socket) { socket.onopen = null; socket.close() } }
  }, [sessionId, persona.id, persona.software_behavior.status, viewerToken, revision])
  return <article className="panel persona-viewer">
    <div className="section-heading"><h2>{persona.synthetic_name}</h2><span className="badge">{mode}</span></div>
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
    {frame ? <figure className="persona-frame">
      <img src={frame.source} alt={`Captured browser view for ${persona.synthetic_name}, session ${sessionId}, frame ${frame.sequence}`} onError={() => { setFrame(null); setError('Captured image could not be decoded.') }} />
      <figcaption>{mode} capture · frame {frame.sequence} · <time dateTime={frame.capturedAt}>{new Date(frame.capturedAt).toLocaleString()}</time>{frameStale ? ' · stale frame' : ''}{mode === 'fixture' ? ' · mock product; not a mandatory experiment trial' : ''}</figcaption>
    </figure> : <div className="persona-no-frame"><strong>Browser frames unavailable</strong><p>No captured browser image is available for this selected session. The room's laptop props are illustrative.</p></div>}
    <h3>Action timeline</h3>
    {session?.actions.length ? <ol>{session.actions.map(action => <li key={action.id} id={`action-${action.id}`}>{action.sequence}. {action.kind}: {action.result} · <time dateTime={action.timestamp}>{new Date(action.timestamp).toLocaleString()}</time><small className="persona-id">Action {action.id}</small></li>)}</ol> : <p className="muted">No executed actions have been recorded.</p>}
    <h3>Feedback</h3><p className="muted">{session?.feedback ? `Synthetic feedback: ${session.feedback.reason}` : 'No trial feedback has been recorded.'}</p>
    {session?.feedback && <p className="muted">Same-session action evidence: {session.feedback.evidence_action_ids.length ? session.feedback.evidence_action_ids.map((id, index) => <span key={id}>{index > 0 ? ', ' : ''}<a href={`#action-${id}`}>{id}</a></span>) : 'none recorded'}</p>}
  </article>
}
