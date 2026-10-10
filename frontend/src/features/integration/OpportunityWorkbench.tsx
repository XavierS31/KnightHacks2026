import { useEffect, useState, type FormEvent } from 'react'
import { request } from '../../shared/api'
import type { components } from '../../shared/api-types'

type Study = components['schemas']['ResearchStudy']
type RepoResearch = components['schemas']['RepositoryResearch']
type Product = components['schemas']['EvaluatedProduct']
const storageKey = 'repofusion-research-study'
const running = (study: Study | null) => study?.status === 'queued' || study?.status === 'running'

function RepoEvidence({ item, momentum }: { item: RepoResearch; momentum?: components['schemas']['MomentumSignal'] }) {
  const brief = item.brief
  return <article className="research-repo">
    <div className="section-heading"><h3><a href={item.repository.url} target="_blank" rel="noreferrer">{item.repository.full_name}</a></h3><span className="badge">{item.status.replaceAll('_', ' ')}</span></div>
    {item.selection_score != null && <p>Source screening score: {item.selection_score}/12</p>}
    {(item.selection_reasons ?? []).length > 0 && <ul>{(item.selection_reasons ?? []).map((reason, i) => <li key={i}>{reason}</li>)}</ul>}
    {brief ? <>
      <p className="repo-summary">{brief.summary}</p>
      <dl className="opportunity-facts">
        <dt>Built for</dt><dd>{brief.original_purpose}</dd>
        <dt>How it works</dt><dd>{brief.distinctive_mechanism}</dd>
        <dt>Takes in → produces</dt><dd>{brief.inputs} → {brief.outputs}</dd>
        <dt>Ways to use it</dt><dd>{brief.interfaces}</dd>
        <dt>Limits on reuse</dt><dd>{brief.reuse_limits}</dd>
      </dl>
    </> : <p>{item.failure ? `Research could not finish: ${item.failure}` : item.status === 'unsuitable' ? 'No reusable foundation passed this candidate’s screening; see the selection reasons.' : item.status === 'not_researched' ? 'Candidate not deeply researched within this run’s selection limits.' : 'This candidate was screened but not deeply researched in this run.'}</p>}
    {(item.source_gaps ?? []).length > 0 && <p role="note">Source coverage gaps: {(item.source_gaps ?? []).join(" · ")}</p>}
    <details><summary>Discovery proof & source evidence</summary>
      <p>{item.origin === 'supporting_tool' && !item.repository.evidence.some(e => e.kind === 'source') ? 'Supporting tool; discovery statistics are unknown.' : `${item.repository.stars.toLocaleString()} stars at discovery. Attention does not establish usefulness.`}</p>
      {momentum && <p>{momentum.current.forks == null ? 'Fork count unknown.' : `${momentum.current.forks.toLocaleString()} forks.`} {momentum.status === 'measured' ? `Net stars: ${momentum.stars_delta}; net forks: ${momentum.forks_delta ?? 'unknown'} over ${momentum.elapsed_hours?.toFixed(1)} hours.` : momentum.note}</p>}
      {item.commit_sha && <p>Pinned commit <a href={`${item.repository.url}/commit/${item.commit_sha}`} target="_blank" rel="noreferrer">{item.commit_sha.slice(0, 12)}</a></p>}
      {item.repository.evidence.filter(e => e.kind === 'source').map((e, i) => <p key={i}><a href={e.reference} target="_blank" rel="noreferrer">Discovery source</a> · {new Date(e.collected_at).toLocaleString()}</p>)}
      {item.evidence?.map(e => <blockquote key={`${e.snapshot_id}:${e.citation_id}`}><p>{e.quote}</p><a href={e.reference} target="_blank" rel="noreferrer">Pinned supporting source</a></blockquote>)}
      <ul>{item.coverage?.map((note, i) => <li key={i}>{note}</li>)}</ul>
      {brief && <p className="muted">AI interpretation of source documents; not independently executed or approved capabilities.</p>}
    </details>
  </article>
}

function ProductReport({ product }: { product: Product }) {
  const idea = product.idea
  return <article className="opportunity-card">
    <div className="section-heading"><span className="eyebrow">{idea.anchor_repository}{(idea.additional_repositories ?? []).length ? ` + ${(idea.additional_repositories ?? []).join(' + ')}` : ''}</span><span className="badge">{product.status.replaceAll('_', ' ')}</span></div>
    <h3>{idea.title}</h3><p className="opportunity-value">{idea.new_use}</p>
    <dl className="opportunity-facts">
      <dt>Who it helps</dt><dd>{idea.audience}</dd>
      <dt>The valuable job</dt><dd>{idea.problem}</dd>
      <dt>A different use</dt><dd>{idea.original_use_difference}</dd>
      <dt>Why these tools</dt><dd>{idea.capability_connection}</dd>
      <dt>What may fail</dt><dd>{idea.risk}</dd>
    </dl>
    {product.critique && <section className="research-verdict"><strong>{product.status === 'rejected' ? 'Why it was rejected' : product.status === 'research_needed' ? 'What remains unresolved' : 'Why investigate this product'}</strong><p>{product.critique.reason}</p><p>Difference from existing tools: {product.critique.difference}</p><p className="muted">Scope: {product.critique.scope.replaceAll('_', ' ')} · Technical support: {product.critique.technical_support} · Existing-solution check: {product.critique.novelty.replaceAll('_', ' ')}</p></section>}
    {product.failure && <p role="note">Evaluation gap: {product.failure}</p>}
    <details className="concept-preview"><summary>See an example of the proposed product</summary>
      <div className="two-columns"><section><h4>Someone provides</h4><p>{idea.example_input}</p></section><section><h4>The product would deliver</h4><p>{idea.example_output}</p></section></div>
      <p><strong>Prototype test:</strong> {idea.prototype_check}</p><p className="muted">Illustrative concept, not an executed example or a persona trial.</p>
    </details>
    <details><summary>Existing-solution research ({product.searches?.length ?? 0} searches)</summary>
      {product.searches?.map((search, index) => <section key={index}><h4>{search.query} · {search.status}</h4><a href={search.reference} target="_blank" rel="noreferrer">Inspect search request</a><p>Collected {new Date(search.collected_at).toLocaleString()}</p>
        {search.failure && <p>Gap: {search.failure}</p>}
        {!(search.matches ?? []).length && <p>No alternative returned in this bounded query.</p>}
        {(search.matches ?? []).map(match => <div key={match.repository}><p><a href={match.url} target="_blank" rel="noreferrer">{match.repository}</a> — {match.description}</p>{match.readme_reference ? <a href={match.readme_reference} target="_blank" rel="noreferrer">Inspected pinned README</a> : <p>README not inspected; comparison remains incomplete.</p>}</div>)}
      </section>)}
      <p>No close match in this GitHub search does not guarantee uniqueness. Commercial tools and the rest of the web may contain equivalents.</p>
    </details>
    <div className="opportunity-gates"><span>Prototype execution: pending</span><span>Persona simulation: pending</span></div>
  </article>
}

export function OpportunityWorkbench() {
  const [mode, setMode] = useState<'fixture' | 'live'>('fixture')
  const [query, setQuery] = useState('stars:>=20')
  const limit = 12
  const [depth, setDepth] = useState(3)
  const [interests, setInterests] = useState('')
  const [study, setStudy] = useState<Study | null>(null)
  const [id, setId] = useState<string | null>(() => sessionStorage.getItem(storageKey))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    request<{ mode: 'fixture' | 'live' }>('/health').then(health => { if (active) setMode(health.mode) }).catch(() => {})
    return () => { active = false }
  }, [])
  useEffect(() => {
    if (!id) return
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    async function poll() {
      try {
        const result = await request<Study>(`/research-studies/${id}`)
        if (!active) return
        setStudy(result); setError('')
        if (running(result)) timer = setTimeout(poll, 2000)
      } catch (failure) {
        if (!active) return
        const message = failure instanceof Error ? failure.message : 'Could not read research progress.'
        setError(message)
        if (message.includes('unknown or no longer retained')) {
          sessionStorage.removeItem(storageKey); setId(null)
          setStudy(current => current && running(current) ? { ...current, status: 'interrupted', stage: 'API restarted; research state was lost. Export retained evidence or start a new run.' } : current)
          return
        }
        timer = setTimeout(poll, 5000)
      }
    }
    void poll()
    return () => { active = false; if (timer) clearTimeout(timer) }
  }, [id])
  async function start(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const result = await request<Study>('/research-studies', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        discovery: { mode, discovery_mode: 'emerging', query, limit },
        research_limit: depth, interests,
      }) })
      setStudy(result); setId(result.id); sessionStorage.setItem(storageKey, result.id)
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Research could not start.') }
    finally { setBusy(false) }
  }
  async function cancel() {
    if (!id) return
    try { setStudy(await request<Study>(`/research-studies/${id}/cancel`, { method: 'POST' })) }
    catch (failure) { setError(failure instanceof Error ? failure.message : 'Cancellation failed.') }
  }
  function download() {
    if (!study) return
    const url = URL.createObjectURL(new Blob([JSON.stringify(study, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a'); link.href = url; link.download = `repofusion-research-${study.id}.json`; link.click(); URL.revokeObjectURL(url)
  }
  const active = busy || running(study)
  const recommended = study?.products?.filter(p => p.status === 'recommended_for_prototype') ?? []
  const other = study?.products?.filter(p => p.status !== 'recommended_for_prototype') ?? []
  const rankedRepos = [...(study?.repositories ?? [])].sort((a, b) => Number(b.status === 'researched') - Number(a.status === 'researched') || Number(Boolean(b.brief)) - Number(Boolean(a.brief)) || (b.selection_score ?? -1) - (a.selection_score ?? -1) || a.repository.full_name.localeCompare(b.repository.full_name))
  const detailedRepos = rankedRepos.filter(r => r.brief || r.status === 'failed' || r.status === 'researching')
  const otherRepos = rankedRepos.filter(r => !detailedRepos.includes(r))
  return <>
    <article className="panel opportunity-intro"><span className="eyebrow">AUTOMATIC OPEN-SOURCE RESEARCH</span><h2>Discover technology. Find a different use.</h2><p>We read the source docs, explain what the tools actually do, explore substantial new products, and compare existing solutions. You start the research; the evaluation runs automatically.</p><div className="opportunity-steps"><span>01 / Discover</span><span>02 / Read & understand</span><span>03 / Repurpose</span><span>04 / Check alternatives</span></div></article>
    <article className="panel"><h2>Start a research run</h2><form className="discovery-form" onSubmit={start}>
      <label>Data mode<select aria-label="Data mode" disabled={active} value={mode} onChange={e => setMode(e.target.value as typeof mode)}><option value="live">Real GitHub + HF research</option><option value="fixture">Fictional workflow demo · no credits</option></select></label>
      <label>GitHub search filter<input disabled={active} required maxLength={200} value={query} onChange={e => setQuery(e.target.value)} /><span className="muted">Recent and active repos; use a language or topic to narrow discovery.</span></label>
      <label>Suitable repos to research<input type="number" min={1} max={6} disabled={active} value={depth} onChange={e => setDepth(Number(e.target.value))} required /></label>
      <label>Optional area of interest<input disabled={active} maxLength={300} value={interests} onChange={e => setInterests(e.target.value)} placeholder="Leave blank to explore broadly" /></label>
      <button disabled={active}>{active ? 'Research in progress…' : mode === 'live' ? 'Discover & research · uses HF credits' : 'Run fictional workflow demo'}</button>
    </form><p className="muted">Screen up to 12 candidates using pinned capabilities and interfaces, then deeply research up to {Math.min(limit, depth)} suitable repos. Up to three replacements, 90 GitHub requests, 13 HF calls and 15 minutes per study. Stars help discovery; they do not rank usefulness. No strong opportunity is a valid result.</p></article>
    {error && <p role="alert">{error}</p>}
    {study && <>
      <article className="panel research-progress" aria-live="polite"><div className="section-heading"><h2>{running(study) ? 'Research is running' : 'Your research report'}</h2><span className="badge">{study.mode} · {study.status}</span></div><p>{study.stage}</p><p className="muted">This report requested {study.request.research_limit} suitable repos from a discovery pool of up to {study.request.discovery.limit}: {study.request.discovery.query}</p><p>{study.counts?.researched ?? 0} repos researched · {study.counts?.suitable_researched ?? 0} suitable for idea evaluation · {study.counts?.research_failures ?? 0} research failures · {study.counts?.unsuitable ?? 0} unsuitable · {study.counts?.source_gaps ?? 0} source gaps · {study.counts?.rejected_ideas ?? 0} ideas rejected · {study.counts?.evaluation_failures ?? 0} evaluation failures · {recommended.length} products worth prototyping</p>{study.mode === 'fixture' && <p><strong>Fictional demonstration. No repo research, inference, alternative search or trial occurred.</strong></p>}{running(study) && <button onClick={cancel}>Cancel research</button>}<button onClick={download}>Export current report</button></article>
      {((study.products ?? []).length > 0 || (!running(study) && study.explanation)) && <article className="panel"><h2>What could you build?</h2><p>{study.explanation}</p>{recommended.map(product => <ProductReport product={product} key={product.id} />)}{!recommended.length && !running(study) && <p>No product passed the available scope and existing-solution checks. We keep the research and rejection reasons rather than inventing a winner.</p>}{other.length > 0 && <details><summary>Ideas rejected or needing more research ({other.length})</summary>{other.map(product => <ProductReport product={product} key={product.id} />)}</details>}</article>}
      {(study.repositories ?? []).length > 0 && <article className="panel"><h2>What we learned about the repositories</h2><p>The descriptions below come from source research. GitHub’s short tagline is not used as the final summary.</p>{detailedRepos.map(item => <RepoEvidence key={item.repository.id} item={item} momentum={study.discovery?.momentum?.find(m => m.current.full_name === item.repository.full_name)} />)}{otherRepos.length > 0 && <details><summary>Other candidates and selection decisions ({otherRepos.length})</summary>{otherRepos.map(item => <RepoEvidence key={item.repository.id} item={item} momentum={study.discovery?.momentum?.find(m => m.current.full_name === item.repository.full_name)} />)}</details>}</article>}
      <details className="panel"><summary>Research coverage, failures and limitations</summary><p>{study.api_requests} GitHub requests · {study.inference_calls} HF calls · {study.counts?.run_failures ?? 0} recorded run failures. Cache hits use no GitHub request.</p><ul>{study.failures?.map((failure, i) => <li key={i}>{failure}</li>)}</ul><ul>{study.limitations?.map(note => <li key={note}>{note}</li>)}</ul>{study.discovery && <ul>{study.discovery.limitations.map(note => <li key={note}>{note}</li>)}</ul>}</details>
    </>}
  </>
}
