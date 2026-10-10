import { useState } from 'react'
import { request, useApi, type EvolutionSummary, type PersonaSummary } from '../../shared/api'
import type { components } from '../../shared/api-types'
import { AsyncState } from '../../shared/AsyncState'

type AnalysisReport = components['schemas']['AnalysisReport']

export default function EvolutionPanel() {
  const { data, error, refresh } = useApi<EvolutionSummary>('/evolution/summary')
  const population = useApi<PersonaSummary>('/personas/summary')
  const [analysis, setAnalysis] = useState<AnalysisReport | null>(null)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const experimentId = population.data?.experiments[0]?.id

  async function analyze() {
    if (!experimentId || running) return
    setRunning(true)
    setAnalysisError(null)
    try {
      const result = await request<AnalysisReport>(`/experiments/${experimentId}/analysis`, {
        method: 'POST',
      })
      setAnalysis(result)
    } catch (failure) {
      setAnalysisError(failure instanceof Error ? failure.message : 'Analysis could not complete.')
    } finally {
      setRunning(false)
    }
  }

  if (!data || error) return <><AsyncState error={error} /><button onClick={refresh}>Retry</button></>
  return <section className="feature-section"><div className="role-flow">{data.roles.map((role, index) =>
    <span key={role}><small>0{index + 1}</small>{role}</span>)}</div>
    <article className="panel">
      <span className="badge">Fixture analysis</span>
      <h3>Start with session evidence</h3>
      <p>Group supplied feedback and inspect its action references. This starter uses deterministic
        grouping; it has no executed trials or model analysis.</p>
      <button onClick={analyze} disabled={!experimentId || running}>
        {running ? 'Checking evidence…' : 'Analyze stored fixture sessions'}
      </button>
      {population.error && <p role="alert">{population.error}</p>}
      {analysisError && <p role="alert">{analysisError}</p>}
      {analysis && <div aria-live="polite">
        <p>{analysis.sessions_seen} supplied sessions · {analysis.feedback_present} with feedback ·
          denominator {analysis.denominator}</p>
        {analysis.clusters.length === 0 && <p>No feedback with action evidence is available.
          No supported improvements were created.</p>}
        {analysis.clusters.map(cluster => <article className="panel" key={cluster.id}>
          <span className="badge">{cluster.category} · fixture</span>
          <h3>{cluster.issue}</h3>
          <p>Heuristic score {cluster.priority_score.toFixed(2)} · affected share
            {' '}{(cluster.affected_share * 100).toFixed(1)}%</p>
          <p>{cluster.supporting_session_ids.length} supporting sessions ·
            {' '}{cluster.evidence_action_ids.length} action references</p>
          <p>{cluster.patch_eligible ? 'Eligible for proposal review.' : 'Context only; no product patch.'}</p>
        </article>)}
        <ul>{analysis.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul>
      </div>}
    </article>
    {data.improvements.map(improvement => <article className="panel" key={improvement.id}>
      <span className="badge">{improvement.status}</span><h3>{improvement.title}</h3><p>{improvement.issue}</p>
      <p className="muted">Supporting session references: {improvement.supporting_session_ids.length}</p></article>)}
    <article className="panel"><h3>Review before v2</h3>
      <p>Keep v1, run fixed regressions, and obtain human review before promoting a patch.
        Patch runs follow proposed → reviewed → patched → regression → human approval. The
        implementer cannot approve its own patch, and a failed regression blocks v2.</p>
      <p>Matched trials: v1 {data.matched_v1} · v2 {data.matched_v2}</p>
    </article>
    <div className="next-gate"><strong>Next gate</strong><p>{data.next_gate}</p></div></section>
}
