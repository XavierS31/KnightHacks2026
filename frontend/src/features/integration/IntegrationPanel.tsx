import { useRef, useState, type FormEvent } from 'react'
import { request, useApi, type IntegrationSummary } from '../../shared/api'
import { AsyncState } from '../../shared/AsyncState'
import type { components } from '../../shared/api-types'
import './discovery.css'
import { ProductAccess } from './ProductAccess'

type DiscoveryRun = components['schemas']['DiscoveryRun']
type DiscoveryRequest = components['schemas']['DiscoveryRequest']

type SourceSnapshot = components['schemas']['SourceSnapshot']
type Extraction = components['schemas']['Extraction']
type ProposalPreview = components['schemas']['ProposalPreview']

function SourceInspector({ runId, repositoryId, onExtraction }: { runId: string; repositoryId: string; onExtraction: (item: Extraction) => void }) {
  const [snapshot, setSnapshot] = useState<SourceSnapshot | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [paths, setPaths] = useState('')
  const [extraction, setExtraction] = useState<Extraction | null>(null)
  const [extracting, setExtracting] = useState(false)

  async function extract() {
    if (!snapshot) return
    setExtracting(true)
    setError(null)
    try {
      const item = await request<Extraction>(`/source-snapshots/${snapshot.id}/extractions`, { method: 'POST' })
      setExtraction(item)
      onExtraction(item)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Capability extraction failed.')
    } finally {
      setExtracting(false)
    }
  }

  async function inspect() {
    setBusy(true)
    setError(null)
    setSnapshot(null)
    setExtraction(null)
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
    <button type="button" disabled={busy || extracting} onClick={inspect}>{busy ? 'Collecting sources…' : 'Inspect sources'}</button></div>
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
      <button type="button" disabled={extracting || busy || !snapshot.documents.some(doc => doc.kind === 'readme' || doc.kind === 'documentation')} onClick={extract}>
        {extracting ? 'Extracting capabilities…' : 'Extract capabilities with HF · uses credits'}
      </button>
      {extraction && <div>
        <h4>Documented capabilities · HF interpretation</h4>
        <p>Requires interface review and execution checks. Not validated.</p>
        {extraction.capabilities.map((capability, i) => <section key={i}>
          <h4>{capability.name}</h4>
          <p>Input: {capability.documented_input}</p><p>Output: {capability.documented_output}</p>
          <blockquote>{capability.source_quote}</blockquote>
          <a href={capability.source_reference} target="_blank" rel="noreferrer">Pinned source</a>
          <p>Uncertainty: {capability.uncertainty}</p>
        </section>)}
      </div>}

    </div>}
  </div>
}

function DiscoveryControls() {
  const [mode, setMode] = useState<'fixture' | 'live'>('fixture')
  const [query, setQuery] = useState('language:Python')
  const [discoveryMode, setDiscoveryMode] = useState<'popular' | 'trending'>('popular')
  const [createdAfter, setCreatedAfter] = useState('')
  const [pushedAfter, setPushedAfter] = useState('')
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'monthly'>('weekly')
  const [language, setLanguage] = useState('')
  const [extractions, setExtractions] = useState<Extraction[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [preview, setPreview] = useState<ProposalPreview | null>(null)
  const [proposing, setProposing] = useState(false)
  const activeRun = useRef<string | null>(null)
  const extractionRevision = useRef(0)

  function retainExtraction(item: Extraction) {
    extractionRevision.current += 1
    setExtractions(current => [...current.filter(old => old.repository_id !== item.repository_id), item])
    setSelectedIds([])
    setPreview(null)
  }

  async function propose() {
    const revision = extractionRevision.current
    setProposing(true)
    setError(null)
    setPreview(null)
    try {
      const result = await request<ProposalPreview>('/proposal-previews', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ extraction_ids: selectedIds }),
      })
      if (extractionRevision.current === revision) setPreview(result)
    } catch (failure) {
      if (extractionRevision.current === revision) setError(failure instanceof Error ? failure.message : 'Proposal generation failed.')
    } finally {
      setProposing(false)
    }
  }

  const [limit, setLimit] = useState(20)
  const [run, setRun] = useState<DiscoveryRun | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function discover(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setRun(null)
    activeRun.current = null
    extractionRevision.current += 1
    setExtractions([])
    setSelectedIds([])
    setPreview(null)
    const body: DiscoveryRequest = {
      mode, discovery_mode: discoveryMode, query, limit, trending_period: period, trending_language: language,
      ...(discoveryMode === 'popular' ? { created_after: createdAfter || null, pushed_after: pushedAfter || null }
        : { trending_period: period, trending_language: language }),
    }
    try {
      const created = await request<DiscoveryRun>('/discovery-runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      const result = await request<DiscoveryRun>(`/discovery-runs/${created.id}`)
      activeRun.current = result.id
      setRun(result)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Discovery failed.')
    } finally {
      setBusy(false)
    }
  }

  return <article className="panel">
    <div className="section-heading"><h2>Repository discovery</h2><span className="badge">Source inspection</span></div>
    <p>Mix established tools, recent projects and Trending snapshots. Source inspection and execution validation are separate steps.</p>
    <form onSubmit={discover} className="discovery-form">
      <label>Data mode<select value={mode} onChange={event => setMode(event.target.value as 'fixture' | 'live')} disabled={busy}>
        <option value="fixture">Synthetic fixture · no network</option><option value="live">Real GitHub metadata</option>
      </select></label>
      <label>Discovery source<select value={discoveryMode} onChange={event => setDiscoveryMode(event.target.value as 'popular' | 'trending')} disabled={busy}>
        <option value="popular">Popular / recent · star-sorted search</option><option value="trending">GitHub Trending snapshot</option>
      </select></label>
      {discoveryMode === 'popular' ? <>
        <label>GitHub search<input value={query} onChange={event => setQuery(event.target.value)} required maxLength={200} disabled={busy} /></label>
        <label>Created on or after<input type="date" value={createdAfter} onChange={event => setCreatedAfter(event.target.value)} disabled={busy} /></label>
        <label>Pushed on or after<input type="date" value={pushedAfter} onChange={event => setPushedAfter(event.target.value)} disabled={busy} /></label>
      </> : <>
        <label>Trending period<select value={period} onChange={event => setPeriod(event.target.value as 'daily' | 'weekly' | 'monthly')} disabled={busy}>
          <option value="daily">Today</option><option value="weekly">This week</option><option value="monthly">This month</option>
        </select></label>
        <label>Language slug (optional)<input value={language} onChange={event => setLanguage(event.target.value)} maxLength={32} placeholder="python" disabled={busy} /></label>
      </>}
      <label>Maximum candidates<input type="number" min={1} max={30} value={limit} onChange={event => setLimit(Number(event.target.value))} disabled={busy} required /></label>
      <button type="submit" disabled={busy || proposing}>{busy ? 'Reading candidates…' : mode === 'fixture' ? 'Load fixture candidates' : 'Search GitHub'}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {run && <div aria-live="polite">
      <p><span className="badge">{run.mode} · {run.status}</span> {run.repositories.length} candidates · {run.cache_hit ? 'cached source metadata' : 'new run'}</p>
      <p className="muted">Source collected {new Date(run.source_collected_at).toLocaleString()}. {run.storage === 'database' ? 'Stored in the database' : 'In-memory retention'}; not a durable job.</p>
      <ul>{run.limitations.map(note => <li key={note}>{note}</li>)}</ul>
      {run.repositories.length === 0 && <p>No repositories matched this search. Try a broader query.</p>}
      {run.repositories.map(repo => <section key={repo.id} className="discovery-candidate">
        <h3>{repo.discovery_mode === 'fixture' ? repo.full_name : <a href={repo.url} target="_blank" rel="noreferrer">{repo.full_name}</a>}</h3>
        <p>{repo.description}</p><p className="muted">{repo.stars.toLocaleString()} stars · {repo.commit_sha ?? 'Search metadata has no pinned commit'}</p>
        {run.mode === 'live' && <SourceInspector key={`${run.id}:${repo.id}`} runId={run.id} repositoryId={repo.id} onExtraction={item => {
          if (activeRun.current === run.id) retainExtraction(item)
        }} />}
        {repo.evidence.map((evidence, index) => <p className="muted" key={index}>
          {evidence.kind} · {evidence.source}: {evidence.note}
          {evidence.kind === 'source' && <><br /><a href={evidence.reference} target="_blank" rel="noreferrer">View source request</a></>}
        </p>)}
      </section>)}
      {extractions.length > 0 && <section>
        <h3>Integration proposals</h3><p>Select 2–10 inspected repositories. Generation uses HF credits.</p>
        {extractions.map(item => <label className="proposal-choice" key={item.id}>
          <input type="checkbox" checked={selectedIds.includes(item.id)} disabled={proposing || (!selectedIds.includes(item.id) && selectedIds.length >= 10)}
            onChange={event => {
              setPreview(null)
              setSelectedIds(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id))
            }} />
          {item.full_name} · {item.commit_sha.slice(0, 12)}
        </label>)}
        <button type="button" disabled={proposing || selectedIds.length < 2} onClick={propose}>{proposing ? 'Generating proposals…' : 'Generate proposal preview · uses credits'}</button>
        {preview && <div aria-live="polite">
          <p>Novelty: unresolved · Feasibility: unreviewed</p>
          {preview.ideas.map((idea, i) => <article key={i}>
            <h4>{idea.title}</h4>
            <p>{extractions.find(item => item.id === idea.first_extraction_id)?.full_name} + {extractions.find(item => item.id === idea.second_extraction_id)?.full_name}</p>
            <p>{idea.problem}</p><p>Audience: {idea.audience}</p>
            <p>Adapter: {idea.adapter_boundary}</p><p>Uncertainty: {idea.uncertainty}</p>
          </article>)}
        </div>}
      </section>}
      <p><strong>Next gate:</strong> {run.next_gate}</p>
    </div>}
  </article>
}

export default function IntegrationPanel() {
  const { data, error, refresh } = useApi<IntegrationSummary>('/integration/summary')
  if (!data || error) return <><AsyncState error={error} /><button onClick={refresh}>Retry</button></>
  return <section className="feature-section">
    <ProductAccess />
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
