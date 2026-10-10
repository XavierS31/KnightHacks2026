import { useEffect, useState, type FormEvent } from 'react'
import { request } from '../../shared/api'
import type { components } from '../../shared/api-types'

type Study = components['schemas']['ResearchStudy']
type DiscoverySource = components['schemas']['DiscoveryRequest']['discovery_mode']
type RepoResearch = components['schemas']['RepositoryResearch']
type Product = components['schemas']['EvaluatedProduct']
const storageKey = 'repofusion-research-study'
const running = (study: Study | null) => study?.status === 'queued' || study?.status === 'running'

function RepoEvidence({ item, momentum }: { item: RepoResearch; momentum?: components['schemas']['MomentumSignal'] }) {
  const brief = item.brief
  return <article className="research-repo">
    <div className="section-heading"><h3><a href={item.repository.url} target="_blank" rel="noreferrer">{item.repository.full_name}</a></h3><span className="badge">{item.status.replaceAll('_', ' ')}</span></div>
    {brief ? <>
      <p className="repo-summary">{brief.summary}</p>
      <dl className="opportunity-facts">
        <dt>Built for</dt><dd>{brief.original_purpose}</dd>
        <dt>How it works</dt><dd>{brief.distinctive_mechanism}</dd>
        <dt>Takes in → produces</dt><dd>{brief.inputs} → {brief.outputs}</dd>
        <dt>Ways to use it</dt><dd>{brief.interfaces}</dd>
        <dt>Limits on reuse</dt><dd>{brief.reuse_limits}</dd>
      </dl>
    </> : <p>{item.failure ? `Research could not finish: ${item.failure}` : item.status === 'not_researched' ? 'Discovered as part of the candidate pool; outside this run’s research limit.' : 'Source research and a readable summary will appear automatically.'}</p>}
    <details><summary>Discovery proof & source evidence</summary>
      <p>{item.origin === 'supporting_tool' ? 'Suggested supporting tool. Source research was attempted; discovery star/fork statistics were not collected.' : `${item.repository.stars.toLocaleString()} stars at discovery. Attention does not establish usefulness.`}</p>
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
    {product.critique && <section className="research-verdict"><strong>{product.status === 'rejected' ? 'Why it was rejected' : product.status === 'research_needed' ? 'What remains unresolved' : 'Why investigate this product'}</strong><p>{product.critique.reason}</p><p>Difference from existing tools: {product.critique.difference}</p><p className="muted">Scope: {product.critique.scope.replaceAll('_', ' ')} · Existing-solution check: {product.critique.novelty.replaceAll('_', ' ')}</p></section>}
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
  const [source, setSource] = useState<DiscoverySource>('emerging')
  const [query, setQuery] = useState('stars:>=100')
  const [limit, setLimit] = useState(3)
  const [depth, setDepth] = useState(3)
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'monthly'>('weekly')
  const [language, setLanguage] = useState('')
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
        discovery: { mode, discovery_mode: source, query, limit, ...(source === 'trending' ? { trending_period: period, trending_language: language } : {}) },
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
  return <>
    <article className="panel opportunity-intro"><span className="eyebrow">AUTOMATIC OPEN-SOURCE RESEARCH</span><h2>Discover technology. Find a different use.</h2><p>We read the source docs, explain what the tools actually do, explore substantial new products, and compare existing solutions. You start the research; the evaluation runs automatically.</p><div className="opportunity-steps"><span>01 / Discover</span><span>02 / Read & understand</span><span>03 / Repurpose</span><span>04 / Check alternatives</span></div></article>
    <article className="panel"><h2>Start a research run</h2><form className="discovery-form" onSubmit={start}>
      <label>Data mode<select aria-label="Data mode" disabled={active} value={mode} onChange={e => setMode(e.target.value as typeof mode)}><option value="live">Real GitHub + HF research</option><option value="fixture">Fictional workflow demo · no credits</option></select></label>
      <label>Discovery source<select aria-label="Discovery source" disabled={active} value={source} onChange={e => setSource(e.target.value as DiscoverySource)}><option value="emerging">Emerging · recent & active</option><option value="trending">GitHub Trending</option><option value="popular">Popular search</option></select></label>
      <label>Candidate pool<input type="number" min={1} max={30} disabled={active} value={limit} onChange={e => setLimit(Number(e.target.value))} required /></label>
      {source === 'trending' ? <><label>Trending window<select aria-label="Trending window" disabled={active} value={period} onChange={e => setPeriod(e.target.value as typeof period)}><option value="daily">Today</option><option value="weekly">This week</option><option value="monthly">This month</option></select></label><label>Language (optional)<input disabled={active} value={language} maxLength={32} onChange={e => setLanguage(e.target.value)} placeholder="python" /></label></> : <label>GitHub search<input disabled={active} required maxLength={200} value={query} onChange={e => setQuery(e.target.value)} /></label>}
      <label>Repos to research<input type="number" min={1} max={6} disabled={active} value={depth} onChange={e => setDepth(Number(e.target.value))} required /></label>
      <label>Optional area of interest<input disabled={active} maxLength={300} value={interests} onChange={e => setInterests(e.target.value)} placeholder="Leave blank to explore broadly" /></label>
      <button disabled={active}>{active ? 'Research in progress…' : mode === 'live' ? 'Discover & research · uses HF credits' : 'Run fictional workflow demo'}</button>
    </form><p className="muted">Up to {Math.min(limit, depth)} discovered repos are researched in depth, plus at most four suggested supporting tools. A bounded run may find no worthwhile product. Emerging uses recent/activity filters; growth requires observations over time.</p></article>
    {error && <p role="alert">{error}</p>}
    {study && <>
      <article className="panel research-progress" aria-live="polite"><div className="section-heading"><h2>{running(study) ? 'Research is running' : 'Your research report'}</h2><span className="badge">{study.mode} · {study.status}</span></div><p>{study.stage}</p><p>{(study.repositories ?? []).filter(r => r.status === 'researched').length} repos researched · {(study.repositories ?? []).filter(r => r.status === 'failed').length} failed · {recommended.length} products worth prototyping</p>{study.mode === 'fixture' && <p><strong>Fictional demonstration. No repo research, inference, alternative search or trial occurred.</strong></p>}{running(study) && <button onClick={cancel}>Cancel research</button>}<button onClick={download}>Export current report</button></article>
      {((study.products ?? []).length > 0 || (!running(study) && study.explanation)) && <article className="panel"><h2>What could you build?</h2><p>{study.explanation}</p>{recommended.map(product => <ProductReport product={product} key={product.id} />)}{!recommended.length && !running(study) && <p>No product passed the available scope and existing-solution checks. We keep the research and rejection reasons rather than inventing a winner.</p>}{other.length > 0 && <details><summary>Ideas rejected or needing more research ({other.length})</summary>{other.map(product => <ProductReport product={product} key={product.id} />)}</details>}</article>}
      {(study.repositories ?? []).length > 0 && <article className="panel"><h2>What we learned about the repositories</h2><p>The descriptions below come from source research. GitHub’s short tagline is not used as the final summary.</p>{(study.repositories ?? []).map(item => <RepoEvidence key={item.repository.id} item={item} momentum={study.discovery?.momentum?.find(m => m.current.full_name === item.repository.full_name)} />)}</article>}
      <details className="panel"><summary>Research coverage, failures and limitations</summary><ul>{study.failures?.map((failure, i) => <li key={i}>{failure}</li>)}</ul><ul>{study.limitations?.map(note => <li key={note}>{note}</li>)}</ul>{study.discovery && <ul>{study.discovery.limitations.map(note => <li key={note}>{note}</li>)}</ul>}</details>
    </>}
  </>
}
