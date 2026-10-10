import { useState, type FormEvent } from 'react'
import { request, useApi, type IntegrationSummary } from '../../shared/api'
import { AsyncState } from '../../shared/AsyncState'
import type { components } from '../../shared/api-types'
import './discovery.css'

type DiscoveryRun = components['schemas']['DiscoveryRun']
type DiscoveryRequest = components['schemas']['DiscoveryRequest']

type SourceSnapshot = components['schemas']['SourceSnapshot']

function SourceInspector({ runId, repositoryId }: { runId: string; repositoryId: string }) {
  const [snapshot, setSnapshot] = useState<SourceSnapshot | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [paths, setPaths] = useState('')

  async function inspect() {
    setBusy(true)
    setError(null)
    setSnapshot(null)
    try {
      setSnapshot(await request<SourceSnapshot>(`/discovery-runs/${runId}/repositories/${repositoryId}/sources`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ documentation_paths: paths.split(',').map(path => path.trim()).filter(Boolean), issue_limit: 5 }),
      }))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Source inspection failed.')
    } finally {
      setBusy(false)
    }
  }

  return <div className="source-inspector">
    <div className="source-controls"><label>Optional documentation paths (up to three, comma-separated)
      <input value={paths} onChange={event => setPaths(event.target.value)} disabled={busy} placeholder="docs/usage.md" />
    </label>
    <button type="button" disabled={busy} onClick={inspect}>{busy ? 'Collecting sources…' : 'Inspect sources'}</button></div>
    {error && <p role="alert">{error}</p>}
    {snapshot && <div aria-live="polite">
      <p><span className="badge">{snapshot.status}</span> Commit <a href={snapshot.commit_reference} target="_blank" rel="noreferrer">{snapshot.commit_sha.slice(0, 12)}</a> · License metadata: {snapshot.license_spdx ?? 'Unavailable'}</p>
      <p>Collected {new Date(snapshot.collected_at).toLocaleString()}</p>
      {snapshot.failures.length > 0 && <ul>{snapshot.failures.map((failure, i) => <li key={i}>{failure}</li>)}</ul>}
      {snapshot.documents.map((document, i) => <details key={i}>
        <summary>{document.kind}: {document.path ?? document.text.split('\n')[0]}{document.truncated ? ' · excerpt truncated' : ''}</summary>
        <a href={document.reference} target="_blank" rel="noreferrer">View source</a>
        <pre className="source-excerpt">{document.text}</pre>
      </details>)}
      <ul>{snapshot.limitations.map(note => <li key={note}>{note}</li>)}</ul>
    </div>}
  </div>
}

function DiscoveryControls() {
  const [mode, setMode] = useState<'fixture' | 'live'>('fixture')
  const [query, setQuery] = useState('language:Python')
  const [limit, setLimit] = useState(20)
  const [run, setRun] = useState<DiscoveryRun | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function discover(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setRun(null)
    const body: DiscoveryRequest = { mode, discovery_mode: 'popular', query, limit }
    try {
      const created = await request<DiscoveryRun>('/discovery-runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      setRun(await request<DiscoveryRun>(`/discovery-runs/${created.id}`))
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Discovery failed.')
    } finally {
      setBusy(false)
    }
  }

  return <article className="panel">
    <div className="section-heading"><h2>Repository discovery</h2><span className="badge">Read-only</span></div>
    <p>Popular search sorts by stars. Trending snapshots, source interfaces, and real integration checks are separate gates.</p>
    <form onSubmit={discover} className="discovery-form">
      <label>Data mode<select value={mode} onChange={event => setMode(event.target.value as 'fixture' | 'live')} disabled={busy}>
        <option value="fixture">Synthetic fixture · no network</option><option value="live">Real GitHub metadata</option>
      </select></label>
      <label>GitHub search<input value={query} onChange={event => setQuery(event.target.value)} required maxLength={200} disabled={busy} /></label>
      <label>Maximum candidates<input type="number" min={1} max={30} value={limit} onChange={event => setLimit(Number(event.target.value))} disabled={busy} required /></label>
      <button type="submit" disabled={busy}>{busy ? 'Reading candidates…' : mode === 'fixture' ? 'Load fixture candidates' : 'Search GitHub'}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {run && <div aria-live="polite">
      <p><span className="badge">{run.mode} · {run.status}</span> {run.repositories.length} candidates · {run.cache_hit ? 'cached source metadata' : 'new run'}</p>
      <p className="muted">Source collected {new Date(run.source_collected_at).toLocaleString()}. {run.storage} retention; not a durable job.</p>
      <ul>{run.limitations.map(note => <li key={note}>{note}</li>)}</ul>
      {run.repositories.length === 0 && <p>No repositories matched this search. Try a broader query.</p>}
      {run.repositories.map(repo => <section key={repo.id} className="discovery-candidate">
        <h3>{repo.discovery_mode === 'fixture' ? repo.full_name : <a href={repo.url} target="_blank" rel="noreferrer">{repo.full_name}</a>}</h3>
        <p>{repo.description}</p><p className="muted">{repo.stars.toLocaleString()} stars · {repo.commit_sha ?? 'Search metadata has no pinned commit'}</p>
        {run.mode === 'live' && <SourceInspector runId={run.id} repositoryId={repo.id} />}
        {repo.evidence.map((evidence, index) => <p className="muted" key={index}>
          {evidence.kind} · {evidence.source}: {evidence.note}
          {evidence.kind === 'source' && <><br /><a href={evidence.reference} target="_blank" rel="noreferrer">View source request</a></>}
        </p>)}
      </section>)}
      <p><strong>Next gate:</strong> {run.next_gate}</p>
    </div>}
  </article>
}

export default function IntegrationPanel() {
  const { data, error, refresh } = useApi<IntegrationSummary>('/integration/summary')
  if (!data || error) return <><AsyncState error={error} /><button onClick={refresh}>Retry</button></>
  return <section className="feature-section">
    <DiscoveryControls />
    <div className="section-heading"><h2>Candidate evidence</h2><span className="badge">{data.mode}</span></div>
    <div className="two-columns">{data.repositories.map(repo => <article className="panel" key={repo.id}>
      <span className="eyebrow">{repo.discovery_mode}</span><h3>{repo.full_name}</h3><p>{repo.description}</p>
      <p className="muted">{repo.evidence[0]?.note}</p></article>)}</div>
    {data.proposals.map(proposal => <article className="panel" key={proposal.id}><h3>{proposal.title}</h3>
      <span className="badge">{proposal.status} · illustrative boundary</span>
      <p>{proposal.problem}</p><div className="contract-line">{proposal.adapter_boundary}</div>
      <p>Novelty: {proposal.novelty} · Feasibility: {proposal.feasibility}</p></article>)}
    <article className="panel"><h3>Validation gates</h3><ol>
      <li>Pin source commits and inspect documented inputs and outputs.</li>
      <li>Record existing-solution research and independently run both sources.</li>
      <li>Validate a narrow adapter with known outputs, invalid inputs and timeouts.</li>
      <li>Publish a factual briefing only after the real product passes fixed checks.</li>
    </ol><p className="muted">The illustrative proposal above has not passed these gates.</p></article>
    <div className="next-gate"><strong>Next gate</strong><p>{data.next_gate}</p></div>
  </section>
}
