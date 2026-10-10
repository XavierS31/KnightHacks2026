export function AsyncState({ error }: { error: string | null }) {
  return <div className="panel" role={error ? 'alert' : 'status'}>
    <h3>{error ? 'API connection unavailable' : 'Loading workspace'}</h3>
    <p>{error ?? 'Reading the shared feature contract…'}</p>
    {error && <p>Start FastAPI on port 8000, then retry the workspace.</p>}
  </div>
}
