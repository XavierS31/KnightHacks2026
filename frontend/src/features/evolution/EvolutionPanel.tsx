import { useState } from 'react'
import { request, useApi, type EvolutionSummary, type PersonaSummary } from '../../shared/api'
import type { components } from '../../shared/api-types'
import { AsyncState } from '../../shared/AsyncState'
import './evolution.css'

type AnalysisReport = components['schemas']['AnalysisReport']

const SOURCE_LABEL = { kickoff_default: 'kickoff default', prioritizer_role: 'prioritizer role' }

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
      <span className="badge">{analysis ? `${analysis.mode} analysis` : 'Session analysis'}</span>
      <h3>Start with session evidence</h3>
      <p>Fixture mode groups supplied feedback with deterministic rules. Live mode reads persisted
        sessions and runs the structured analyst, prioritizer and UX reviewer roles. Deterministic
        checks reject any role output that cites evidence outside its own sessions.</p>
      <button onClick={analyze} disabled={!experimentId || running}>
        {running ? 'Checking evidence…' : 'Analyze stored sessions'}
      </button>
      {population.error && <p role="alert">{population.error}</p>}
      {analysisError && <p role="alert">{analysisError}</p>}
      {analysis && <div aria-live="polite">
        <p>{analysis.sessions_seen} sessions · {analysis.feedback_present} with feedback ·
          denominator {analysis.denominator} · {analysis.inference_used
            ? `${analysis.role_runs.length} HF role calls` : 'no model inference'}</p>
        <p className="contract-line">priority = {analysis.priority_formula}</p>
        {analysis.clusters.length === 0 && <p>No feedback with action evidence was grouped.
          No supported improvements were created.</p>}
        {analysis.clusters.map(cluster => <article className="panel" key={cluster.id}>
          <span className="badge">{cluster.category} · {analysis.mode}</span>
          <h3>{cluster.issue}</h3>
          <div className="heuristics" aria-label="Heuristic priority inputs">
            <div><strong>{cluster.severity}</strong>
              <span>severity · {SOURCE_LABEL[cluster.severity_source]}</span></div>
            <div><strong>{(cluster.affected_share * 100).toFixed(1)}%</strong>
              <span>affected share · computed</span></div>
            <div><strong>{(cluster.evidence_strength * 100).toFixed(0)}%</strong>
              <span>evidence strength · computed</span></div>
            <div><strong>{cluster.estimated_effort_hours} h</strong>
              <span>effort · {SOURCE_LABEL[cluster.effort_source]}</span></div>
            <div><strong>{cluster.priority_score.toFixed(2)}</strong>
              <span>heuristic score</span></div>
          </div>
          <p>{cluster.supporting_session_ids.length} supporting sessions ·
            {' '}{cluster.evidence_action_ids.length} cited actions</p>
          {cluster.analyst_rationale && <p className="muted">Analyst: {cluster.analyst_rationale}</p>}
          {cluster.priority_rationale && <p className="muted">Prioritizer: {cluster.priority_rationale}</p>}
          <p>{cluster.patch_eligible ? 'Evidenced product defect; eligible for proposal review.'
            : cluster.category === 'product' ? 'Evidence incomplete; no proposal.'
              : 'Context only; no product patch.'}</p>
        </article>)}
        {analysis.unclustered_feedback_ids.length > 0 && <p className="muted">
          {analysis.unclustered_feedback_ids.length} feedback items supported no finding.</p>}
        {analysis.proposals.map(proposal => <article className="panel" key={proposal.id}>
          <span className="badge">{proposal.supported ? 'Supported draft' : 'Unsupported draft'}</span>
          <h3>{proposal.title}</h3>
          <p>{proposal.problem}</p>
          <p><strong>Change:</strong> {proposal.change}</p>
          <p><strong>Acceptance check:</strong> {proposal.acceptance_check}</p>
          <p className="muted">{proposal.support_note}</p>
        </article>)}
        {analysis.role_runs.length > 0 && <ul className="role-runs" aria-label="Role provenance">
          {analysis.role_runs.map(run => <li key={run.request_id}>
            {run.role} · {run.model_id} via {run.provider} · {run.prompt_version} ·
            {' '}{run.latency_ms} ms · retries {run.retry_count}</li>)}
        </ul>}
        <ul>{analysis.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul>
      </div>}
    </article>
    {data.improvements.map(improvement => <article className="panel" key={improvement.id}>
      <span className="badge">{improvement.status}</span><h3>{improvement.title}</h3><p>{improvement.issue}</p>
      <p className="muted">Supporting session references: {improvement.supporting_session_ids.length}</p></article>)}
    <article className="panel"><h3>Review before v2</h3>
      <p>Keep v1, run fixed regressions, and obtain human review before promoting a patch.
        The starter approval route rejects promotion until those gates exist.</p>
      <p>Matched trials: v1 {data.matched_v1} · v2 {data.matched_v2}</p>
    </article>
    <div className="next-gate"><strong>Next gate</strong><p>{data.next_gate}</p></div></section>
}
