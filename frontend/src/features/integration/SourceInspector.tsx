import { useState } from 'react'
import { request } from '../../shared/api'
import type { components } from '../../shared/api-types'
type SourceSnapshot = components['schemas']['SourceSnapshot']
export function SourceInspector({ runId, repositoryId, onSnapshot }: { runId: string; repositoryId: string; onSnapshot: (item: SourceSnapshot) => void }) {
  const [snapshot, setSnapshot] = useState<SourceSnapshot | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [paths, setPaths] = useState('')
  async function inspect() {
    setBusy(true)
    setError(null)
    setSnapshot(null)
    try {
      const collected = await request<SourceSnapshot>(`/discovery-runs/${runId}/repositories/${repositoryId}/sources`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ documentation_paths: paths.split(',').map(path => path.trim()).filter(Boolean), issue_limit: 5 }),
      })
      setSnapshot(collected)
      onSnapshot(collected)
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

