import { useRef, useState, type FormEvent } from 'react'
import { request } from '../../shared/api'
import type { components } from '../../shared/api-types'
import { SourceInspector } from './SourceInspector'

type Run = components['schemas']['DiscoveryRun']
type Snapshot = components['schemas']['SourceSnapshot']
type Report = components['schemas']['OpportunityReport']
type Card = components['schemas']['OpportunityCard']
type DiscoverySource = components['schemas']['DiscoveryRequest']['discovery_mode']

function OpportunityReview({ card, report, onDecision }: { card: Card; report: Report; onDecision: (report: Report) => void }) {
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function decide(decision: 'shortlisted' | 'rejected') {
    setBusy(true); setError('')
    try {
      onDecision(await request<Report>(`/opportunity-reports/${report.id}/cards/${card.id}/decision`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, note }),
      }))
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Decision failed.') }
    finally { setBusy(false) }
  }
  return <article className="opportunity-card">
    <div className="section-heading"><span className="eyebrow">{card.kind.replace('_', ' ')} · {card.need_basis.replace('_', ' ')}</span><span className="badge">{card.decision}</span></div>
    <h3>{card.title}</h3><p className="opportunity-value">{card.proposed_value}</p>
    <dl className="opportunity-facts">
      <dt>For whom</dt><dd>{card.audience}</dd>
      <dt>The problem</dt><dd>{card.problem}</dd>
      <dt>Already possible</dt><dd>{card.current_value}</dd>
      <dt>Why investigate now</dt><dd>{card.why_now}</dd>
      <dt>What to build</dt><dd>{card.implementation_boundary}</dd>
      <dt>What could invalidate it</dt><dd>{card.risk}</dd>
    </dl>
    <details><summary>Inspect supporting evidence ({card.evidence.length})</summary>
      {card.evidence.length === 0 && <p>Fictional fixture: no real source citations.</p>}
      {card.evidence.map(item => <blockquote key={item.citation_id}>
        <p>{item.quote}</p><a href={item.reference} target="_blank" rel="noreferrer">{item.repository} · {item.kind}</a>
        <p className="muted">{item.kind === 'issue' ? `Issue state: ${item.issue_state ?? 'unknown'} · collection-time report` : `Commit ${item.commit_sha.slice(0, 12)}`} · {new Date(item.collected_at).toLocaleString()}</p>
      </blockquote>)}
      <p>Citations resolve to collected excerpts. Their support for this interpretation still needs review.</p>
    </details>
    <details className="concept-preview"><summary>Preview the proposed workflow · illustrative</summary>
      <div className="two-columns"><section><h4>Example input</h4><p>{card.example_input}</p></section><section><h4>Expected outcome</h4><p>{card.example_output}</p></section></div>
      <p><strong>Test that could fail:</strong> {card.acceptance_check}</p>
      <p className="muted">This describes a concept. No source code, adapter or persona session executed this example.</p>
    </details>
    <div className="opportunity-gates"><span>Alternatives: {card.novelty}</span><span>Feasibility: {card.feasibility}</span><span>Execution: pending</span><span>Simulation: pending</span></div>
    <label className="decision-note">Your review reason<textarea value={note} maxLength={1000} onChange={event => setNote(event.target.value)} placeholder="Why is this worth investigating—or why should we discard it?" disabled={busy} /></label>
    <div className="review-actions"><button disabled={busy || !note.trim()} onClick={() => decide('shortlisted')}>Shortlist for investigation</button><button disabled={busy || !note.trim()} onClick={() => decide('rejected')}>Reject opportunity</button></div>
    {card.decision_note && <p>Your decision: {card.decision_note}</p>}
    {card.decision === 'shortlisted' && <p className="muted">Next: research alternatives, review interfaces/licenses, execute known checks, then hand a frozen product briefing to persona testing. Shortlisting does not launch trials.</p>}
    {error && <p role="alert">{error}</p>}
  </article>
}

export function OpportunityWorkbench() {
  const [mode, setMode] = useState<'fixture' | 'live'>('fixture')
  const [source, setSource] = useState<DiscoverySource>('emerging')
  const [query, setQuery] = useState('language:Python stars:>=100')
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'monthly'>('weekly')
  const [language, setLanguage] = useState('')
  const [created, setCreated] = useState('')
  const [pushed, setPushed] = useState('')
  const [limit, setLimit] = useState(20)
  const [interests, setInterests] = useState('')
  const [run, setRun] = useState<Run | null>(null)
  const [snapshots, setSnapshots] = useState<Snapshot[]>([])
  const [anchor, setAnchor] = useState('')
  const [supporting, setSupporting] = useState<string[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState('')
  const revision = useRef(0)
  const activeRun = useRef<string | null>(null)
  function invalidate() { revision.current += 1; setReport(null) }
  async function discover(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); invalidate()
    setRun(null); activeRun.current = null; setSnapshots([]); setAnchor(''); setSupporting([])
    try {
      const result = await request<Run>('/discovery-runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        mode, discovery_mode: source, query, limit,
        ...(source === 'trending' ? { trending_period: period, trending_language: language }
          : { created_after: created || null, pushed_after: pushed || null }),
      }) })
      activeRun.current = result.id; setRun(result)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Discovery failed.') }
    finally { setBusy(false) }
  }
  function retain(snapshot: Snapshot) {
    invalidate()
    setSnapshots(current => [...current.filter(item => item.repository_id !== snapshot.repository_id), snapshot])
    setAnchor(snapshot.id); setSupporting([])
  }
  async function analyze(demo = false) {
    const expected = revision.current
    setAnalyzing(true); setError(''); setReport(null)
    try {
      const result = await request<Report>(demo ? '/integration/opportunity-demo' : '/opportunity-reports', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        ...(demo ? {} : { body: JSON.stringify({ anchor_snapshot_id: anchor, supporting_snapshot_ids: supporting, interests }) }),
      })
      if (revision.current === expected) setReport(result)
    } catch (failure) { if (revision.current === expected) setError(failure instanceof Error ? failure.message : 'Opportunity analysis failed.') }
    finally { setAnalyzing(false) }
  }
  function download() {
    if (!report) return
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a'); link.href = url; link.download = `opportunity-${report.id}.json`; link.click(); URL.revokeObjectURL(url)
  }
  return <>
    <article className="panel opportunity-intro"><span className="eyebrow">OPEN-SOURCE OPPORTUNITY LAB</span>
      <h2>Find what you could build next.</h2><p>Explore emerging tools, inspect the problems around them, and investigate a useful extension. Add another repository only when it contributes something necessary.</p>
      <div className="opportunity-steps"><span>01 / Discover</span><span>02 / Investigate</span><span>03 / Preview</span><span>04 / Test & observe</span></div>
      <button disabled={busy || analyzing} onClick={() => { invalidate(); void analyze(true) }}>Explore a fictional example · no credits</button>
    </article>
    <article className="panel"><div className="section-heading"><h2>Discover an anchor repository</h2><span className="badge">Read-only discovery</span></div>
      <form className="discovery-form" onSubmit={discover}>
        <label>Data mode<select value={mode} disabled={busy || analyzing} onChange={event => setMode(event.target.value as 'fixture' | 'live')}><option value="fixture">Synthetic candidates · no network</option><option value="live">Real GitHub reads</option></select></label>
        <label>Discovery source<select value={source} disabled={busy || analyzing} onChange={event => setSource(event.target.value as DiscoverySource)}><option value="emerging">Emerging candidates · recent & active</option><option value="trending">GitHub Trending snapshot</option><option value="popular">Popular · star-sorted search</option></select></label>
        <label>Maximum candidates<input type="number" min={1} max={30} required value={limit} disabled={busy || analyzing} onChange={event => setLimit(Number(event.target.value))} /></label>
        {source === 'trending' ? <><label>Window<select value={period} onChange={event => setPeriod(event.target.value as typeof period)} disabled={busy || analyzing}><option value="daily">Today</option><option value="weekly">This week</option><option value="monthly">This month</option></select></label><label>Language slug<input value={language} maxLength={32} placeholder="python" onChange={event => setLanguage(event.target.value)} disabled={busy || analyzing} /></label></> : <>
          <label>GitHub search<input required maxLength={200} value={query} disabled={busy || analyzing} onChange={event => setQuery(event.target.value)} /></label>
          <label>Created since<input type="date" value={created} disabled={busy || analyzing} onChange={event => setCreated(event.target.value)} /></label>
          <label>Active since<input type="date" value={pushed} disabled={busy || analyzing} onChange={event => setPushed(event.target.value)} /></label>
        </>}
        <button disabled={busy || analyzing}>{busy ? 'Reading candidates…' : mode === 'fixture' ? 'Load fixture candidates' : 'Discover repositories'}</button>
      </form>
      <p className="muted">Emerging defaults: created within 90 days and pushed within 30 days. Attention is a discovery signal, not evidence of demand. Growth requires comparable observations.</p>
      {run && <div aria-live="polite"><p><span className="badge">{run.mode}</span> {run.repositories.length} candidates · {run.cache_hit ? 'cached' : 'new source read'}</p>
        {run.request.discovery_mode === 'emerging' && <p>Effective dates: created ≥ {run.request.created_after}; pushed ≥ {run.request.pushed_after}.</p>}
        {run.repositories.length === 0 && <p>No candidates found. Broaden your filters.</p>}
        <details><summary>Source coverage and limitations</summary><ul>{run.limitations.map(note => <li key={note}>{note}</li>)}</ul></details>
        {run.repositories.map(repo => {
          const growth = (run.momentum ?? []).find(item => item.current.full_name === repo.full_name)
          return <section className="discovery-candidate" key={repo.id}>
            <h3>{run.mode === 'live' ? <a href={repo.url} target="_blank" rel="noreferrer">{repo.full_name}</a> : repo.full_name}</h3><p>{repo.description}</p>
            <p>{repo.stars.toLocaleString()} stars · {growth?.current.forks == null ? 'Fork count unavailable' : `${growth.current.forks.toLocaleString()} forks`}</p>
            {growth?.status === 'measured' ? <p className="growth-measured">Net stars: {growth.stars_delta! >= 0 ? '+' : ''}{growth.stars_delta} · Net forks: {growth.forks_delta ?? 'unknown'} over {growth.elapsed_hours?.toFixed(1)} hours. Baseline {new Date(growth.baseline!.observed_at).toLocaleString()} → {new Date(growth.current.observed_at).toLocaleString()}</p> : <p className="muted">Growth: {growth?.status.replaceAll('_', ' ') ?? 'unknown'}. {growth?.note}</p>}
            {repo.evidence.filter(item => item.kind === 'source').map((item, i) => <p key={i}><a href={item.reference} target="_blank" rel="noreferrer">Metadata source</a> · {new Date(item.collected_at).toLocaleString()}</p>)}
            {run.mode === 'live' && <SourceInspector key={`${run.id}:${repo.id}`} runId={run.id} repositoryId={repo.id} onSnapshot={snapshot => { if (activeRun.current === run.id) retain(snapshot) }} />}
          </section>
        })}
      </div>}
    </article>
    {snapshots.length > 0 && <article className="panel"><h2>Investigate an opportunity</h2><p>One anchor is enough. Supporting tools are optional; inspect their sources above before selecting them.</p>
      <div className="discovery-form"><label>Anchor repository<select value={anchor} disabled={analyzing} onChange={event => { invalidate(); setAnchor(event.target.value); setSupporting([]) }}>{snapshots.map(item => <option value={item.id} key={item.id}>{item.full_name}</option>)}</select></label>
        <label>Optional interests or constraints<input value={interests} maxLength={300} disabled={analyzing} placeholder="Developer tools, offline use, weekend-sized…" onChange={event => { invalidate(); setInterests(event.target.value) }} /></label>
      </div>
      {snapshots.filter(item => item.id !== anchor).map(item => <label className="proposal-choice" key={item.id}><input type="checkbox" checked={supporting.includes(item.id)} disabled={analyzing || (!supporting.includes(item.id) && supporting.length >= 2)} onChange={event => { invalidate(); setSupporting(current => event.target.checked ? [...current, item.id] : current.filter(id => id !== item.id)) }} />Optional supporting repo: {item.full_name}</label>)}
      <button disabled={busy || analyzing || !anchor} onClick={() => analyze()}>{analyzing ? 'Investigating evidence…' : 'Find opportunities with HF · uses credits'}</button>
      <p className="muted">The model may return no worthwhile opportunity. Documentation and sampled issue reports are evidence inputs; no automatic demand or uniqueness claim.</p>
    </article>}
    {error && <p role="alert">{error}</p>}
    {report && <article className="panel" aria-live="polite"><div className="section-heading"><h2>Opportunities around {report.anchor_repository}</h2><span className="badge">{report.mode} · hypotheses</span></div>
      <p>{report.anchor_commit ? `Pinned anchor ${report.anchor_commit.slice(0, 12)} · ` : ''}Created {new Date(report.created_at).toLocaleString()}</p>
      {report.opportunities.length === 0 && <p>No worthwhile opportunity retained: {report.no_opportunity_reason}</p>}
      {report.opportunities.map(card => <OpportunityReview key={`${report.id}:${card.id}`} card={card} report={report} onDecision={updated => setReport(current => current?.id === updated.id ? updated : current)} />)}
      {report.research_leads.length > 0 && <><h3>Unverified research leads</h3><ul>{report.research_leads.map(lead => <li key={lead}>{lead}</li>)}</ul></>}
      <details><summary>Provenance and limits</summary><pre className="source-excerpt">{JSON.stringify(report.provenance, null, 2)}</pre><ul>{report.limitations.map(note => <li key={note}>{note}</li>)}</ul></details>
      <button onClick={download}>Export opportunity report</button><p className="muted">Reports and decisions are in memory. Export preserves this hypothesis and review; it is not a validated persona handoff.</p>
    </article>}
  </>
}
