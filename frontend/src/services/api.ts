
const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || '/api'
).replace(/\/$/, '')

export type Incident = {
  id: number
  title: string
  description: string
  service: string
  environment: 'production' | 'staging' | 'development' | null
  severity: 'low' | 'medium' | 'high' | 'critical'
  status: 'open' | 'investigating' | 'resolved'
  created_at: string
}

export type IncidentForm = {
  title: string
  description: string
  service: string
  environment: '' | 'production' | 'staging' | 'development'
  severity: Incident['severity']
}

export type EvidenceSourceType =
  | 'log'
  | 'metric'
  | 'trace'
  | 'deployment'
  | 'note'

export type IncidentEvidence = {
  id: number
  incident_id: number
  source_type: EvidenceSourceType
  content: string
  created_at: string
}

export type EvidenceForm = {
  source_type: EvidenceSourceType
  content: string
}

export type AIConfidence = 'low' | 'medium' | 'high'

export type AIFact = {
  statement: string
  evidence_ids: number[]
}

export type AIHypothesis = {
  explanation: string
  supporting_evidence_ids: number[]
  confidence: AIConfidence
}

export type AIInvestigationResult = {
  observed_facts: AIFact[]
  hypotheses: AIHypothesis[]
  recommended_checks: string[]
  unknowns: string[]
}

export type InvestigationHistoryRecord = {
  id: number
  incident_id: number
  result: AIInvestigationResult
  created_at: string
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PATCH'
  body?: unknown
}

async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers: HeadersInit = {}

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  let response: Response

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body:
        options.body !== undefined
          ? JSON.stringify(options.body)
          : undefined,
    })
  } catch {
    throw new Error(
      'Unable to connect to the OpsPilot API. Check that the backend is running.',
    )
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`

    try {
      const errorBody = await response.json()

      if (typeof errorBody.detail === 'string') {
        message = errorBody.detail
      } else if (Array.isArray(errorBody.detail)) {
        message = 'The server rejected the submitted data. Please check your input.'
      }
    } catch {
      // Keep the fallback message if the response is not JSON.
    }

    throw new Error(message)
  }

  return response.json() as Promise<T>
}

export function getIncidents(): Promise<Incident[]> {
  return request<Incident[]>('/incidents')
}

export function createIncident(
  data: IncidentForm,
): Promise<Incident> {
  return request<Incident>('/incidents', {
    method: 'POST',
    body: data,
  })
}

export function getIncidentEvidence(
  incidentId: number,
): Promise<IncidentEvidence[]> {
  return request<IncidentEvidence[]>(
    `/incidents/${incidentId}/evidence?limit=50&offset=0`,
  )
}

export function createIncidentEvidence(
  incidentId: number,
  data: EvidenceForm,
): Promise<IncidentEvidence> {
  return request<IncidentEvidence>(
    `/incidents/${incidentId}/evidence`,
    {
      method: 'POST',
      body: data,
    },
  )
}

export function getInvestigationHistory(
  incidentId: number,
): Promise<InvestigationHistoryRecord[]> {
  return request<InvestigationHistoryRecord[]>(
    `/incidents/${incidentId}/investigations`,
  )
}

export function runIncidentInvestigation(
  incidentId: number,
): Promise<AIInvestigationResult> {
  return request<AIInvestigationResult>(
    `/incidents/${incidentId}/investigate`,
    {
      method: 'POST',
    },
  )
}

export function updateIncidentStatus(
  incidentId: number,
  status: Incident['status'],
): Promise<Incident> {
  return request<Incident>(`/incidents/${incidentId}`, {
    method: 'PATCH',
    body: { status },
  })
}
