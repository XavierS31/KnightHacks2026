import { useApi } from '../../shared/api'
import type { components } from '../../shared/api-types'

type ProductReadiness = components['schemas']['ProductReadiness']

export function ProductAccess() {
  const { data, error, refresh } = useApi<ProductReadiness>('/integration/product-readiness')
  return <article className="panel">
    <div className="section-heading"><h2>SourceTable · product v1</h2><span className="badge">{data?.status ?? 'Checking manifest'}</span></div>
    <p>Extract one ruled PDF table, validate column types and trace errors to source cells.</p>
    <p className="muted">{error ?? data?.message}</p>
    {data?.version && <>
      <p>{data.version.briefing}</p>
      <a href={data.runtime_url} target="_blank" rel="noreferrer">Open the separate local product</a>
      <ul>{data.version.limitations.map(note => <li key={note}>{note}</li>)}</ul>
    </>}
    {error && <button onClick={refresh}>Retry manifest check</button>}
  </article>
}
