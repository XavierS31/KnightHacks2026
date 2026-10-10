import { useState } from 'react'
import { useApi, type PersonaSummary } from '../../shared/api'
import { AsyncState } from '../../shared/AsyncState'
import PersonaWorld from './PersonaWorld'
import SessionViewer from './SessionViewer'
import './personas.css'

export default function PersonaPanel() {
  const { data, error, refresh } = useApi<PersonaSummary>('/personas/summary')
  const [selection, setSelection] = useState('')
  const [tokenInput, setTokenInput] = useState('')
  const [viewerToken, setViewerToken] = useState('')
  if (!data || error) return <><AsyncState error={error} /><button onClick={refresh}>Retry</button></>
  const selected = data.personas.find(persona => persona.id === selection) ?? data.personas[0]
  const session = data.sessions.find(item => item.persona_id === selected?.id)
  return <section className="feature-section persona-section"><div className="metrics">
    <div><strong>{data.target_population}</strong><span>Required per version</span></div>
    <div><strong>{data.featured_count}</strong><span>Featured characters</span></div>
    <div><strong>{data.experiments.reduce((sum, item) => sum + item.counts.completed, 0)}</strong><span>Completed trials</span></div></div>
    <article className="panel"><div className="section-heading"><h2>Synthetic campus</h2><span className="badge">{data.mode}</span></div>
      <p className="muted">Ten fictional characters, linked to fixture session IDs. Select a character or use the buttons. Drag to orbit. Rooms: library, classroom, home, office.</p>
      {selected && <PersonaWorld personas={data.personas} selected={selected.id} onSelect={setSelection} />}
      <div className="persona-selector" aria-label="Select persona">{data.personas.slice(0, 10).map(persona => <button key={persona.id}
        aria-pressed={persona.id === selected?.id} onClick={() => setSelection(persona.id)}>
        {persona.synthetic_name}<small>{persona.cohort} · {persona.scenario.location_id}</small>
      </button>)}</div>
    </article>
    <form className="persona-auth" onSubmit={event => { event.preventDefault(); setViewerToken(tokenInput) }}>
      <label htmlFor="viewer-token">Viewer token (leave empty for local fixture)</label>
      <input id="viewer-token" type="password" autoComplete="off" value={tokenInput} onChange={event => setTokenInput(event.target.value)} />
      <button type="submit">Connect viewer</button>
      <small>Held in memory only. Never enter your Hugging Face token here.</small>
    </form>
    {selected && session ? <SessionViewer key={session.id} persona={selected} sessionId={session.id} viewerToken={viewerToken} /> : <p>No session linked to this persona.</p>}
    <div className="next-gate"><strong>Next gate</strong><p>{data.next_gate}</p></div></section>
}
