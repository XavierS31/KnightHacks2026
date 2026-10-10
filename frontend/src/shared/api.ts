import { useEffect, useState } from 'react'
import type { components } from './api-types'

export type IntegrationSummary = components['schemas']['IntegrationSummary']
export type PersonaSummary = components['schemas']['PersonaSummary']
export type EvolutionSummary = components['schemas']['EvolutionSummary']
export type Persona = components['schemas']['Persona']
export type Session = components['schemas']['Session']

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, init)
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new Error(error?.error?.message ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export function useApi<T>(path: string) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    let active = true
    setError(null)
    request<T>(path).then(result => { if (active) setData(result) })
      .catch((failure: Error) => { if (active) setError(failure.message) })
    return () => { active = false }
  }, [path, revision])
  return { data, error, refresh: () => setRevision(value => value + 1) }
}
