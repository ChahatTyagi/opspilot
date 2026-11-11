import { useEffect, useMemo, useState, type FormEvent } from 'react'
import './App.css'

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || '/api'
).replace(/\/$/, '')

type Incident = {
  id: number
  title: string
  description: string
  service: string
  environment: 'production' | 'staging' | 'development' | null
  severity: 'low' | 'medium' | 'high' | 'critical'
  status: 'open' | 'investigating' | 'resolved'
  created_at: string
}

type IncidentForm = {
  title: string
  description: string
  service: string
  environment: '' | 'production' | 'staging' | 'development'
  severity: Incident['severity']
}

type EvidenceSourceType = 'log' | 'metric' | 'trace' | 'deployment' | 'note'

type IncidentEvidence = {
  id: number
  incident_id: number
  source_type: EvidenceSourceType
  content: string
  created_at: string
}

type EvidenceForm = {
  source_type: EvidenceSourceType
  content: string
}

type AIConfidence = 'low' | 'medium' | 'high'

type AIFact = {
  statement: string
  evidence_ids: number[]
}

type AIHypothesis = {
  explanation: string
  supporting_evidence_ids: number[]
  confidence: AIConfidence
}

type AIInvestigationResult = {
  observed_facts: AIFact[]
  hypotheses: AIHypothesis[]
  recommended_checks: string[]
  unknowns: string[]
}

type WorkspacePage = 'overview' | 'incidents'
type IncidentStatusFilter = 'all' | Incident['status']
type IncidentSeverityFilter = 'all' | Incident['severity']
type IncidentEnvironmentFilter = 'all' | NonNullable<Incident['environment']>
type IncidentSortOption = 'newest' | 'oldest' | 'severity-high' | 'severity-low'

const navigationItems: {
  id: WorkspacePage
  label: string
  icon: string
}[] = [
  { id: 'overview', label: 'Overview', icon: '▦' },
  { id: 'incidents', label: 'Incidents', icon: '◉' },
]

const emptyForm: IncidentForm = {
  title: '',
  description: '',
  service: '',
  environment: '',
  severity: 'medium',
}

const emptyEvidenceForm: EvidenceForm = {
  source_type: 'log',
  content: '',
}

const severityRank: Record<Incident['severity'], number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
}

function formatDate(value: string) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return 'Unknown date'
  }

  return date.toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  })
}

function App() {
  const [activePage, setActivePage] = useState<WorkspacePage>('overview')
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [form, setForm] = useState<IncidentForm>(emptyForm)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selectedIncidentId, setSelectedIncidentId] = useState<number | null>(null)

  const selectedIncident =
    incidents.find((incident) => incident.id === selectedIncidentId) ?? null

  const [isLoadingIncidents, setIsLoadingIncidents] = useState(true)
  const [loadError, setLoadError] = useState('')

  const [evidence, setEvidence] = useState<IncidentEvidence[]>([])
  const [isLoadingEvidence, setIsLoadingEvidence] = useState(false)
  const [evidenceLoadError, setEvidenceLoadError] = useState('')
  const [evidenceForm, setEvidenceForm] =
    useState<EvidenceForm>(emptyEvidenceForm)
  const [isSubmittingEvidence, setIsSubmittingEvidence] = useState(false)
  const [evidenceSubmitError, setEvidenceSubmitError] = useState('')

  const [investigationResult, setInvestigationResult] =
    useState<AIInvestigationResult | null>(null)
  const [isInvestigating, setIsInvestigating] = useState(false)
  const [investigationError, setInvestigationError] = useState('')

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [updatingIncidentIds, setUpdatingIncidentIds] = useState<number[]>([])
  const [statusUpdateErrors, setStatusUpdateErrors] =
    useState<Record<number, string>>({})

  const [statusFilter, setStatusFilter] =
    useState<IncidentStatusFilter>('all')
  const [severityFilter, setSeverityFilter] =
    useState<IncidentSeverityFilter>('all')
  const [environmentFilter, setEnvironmentFilter] =
    useState<IncidentEnvironmentFilter>('all')
  const [sortOption, setSortOption] =
    useState<IncidentSortOption>('newest')

  useEffect(() => {
    let isActive = true

    async function loadIncidents() {
      setLoadError('')
      setIsLoadingIncidents(true)

      try {
        const response = await fetch(`${API_BASE_URL}/incidents`)

        if (!response.ok) {
          throw new Error('Unable to load incidents. Please try again.')
        }

        const loadedIncidents: Incident[] = await response.json()

        if (isActive) {
          setIncidents(loadedIncidents)
        }
      } catch (requestError) {
        if (isActive) {
          setLoadError(
            requestError instanceof Error
              ? requestError.message
              : 'An unexpected error occurred while loading incidents.',
          )
        }
      } finally {
        if (isActive) {
          setIsLoadingIncidents(false)
        }
      }
    }

    void loadIncidents()

    return () => {
      isActive = false
    }
  }, [])

  useEffect(() => {
    if (selectedIncidentId === null) {
      setEvidence([])
      setEvidenceLoadError('')
      setIsLoadingEvidence(false)
      setInvestigationResult(null)
      setInvestigationError('')
      return
    }

    let isActive = true

    async function loadEvidence() {
      setEvidence([])
      setEvidenceLoadError('')
      setIsLoadingEvidence(true)
      setInvestigationResult(null)
      setInvestigationError('')

      try {
        const response = await fetch(
          `${API_BASE_URL}/incidents/${selectedIncidentId}/evidence?limit=50&offset=0`,
        )

        if (!response.ok) {
          throw new Error('Unable to load evidence. Please try again.')
        }

        const loadedEvidence: IncidentEvidence[] = await response.json()

        if (isActive) {
          setEvidence(loadedEvidence)
        }
      } catch (requestError) {
        if (isActive) {
          setEvidenceLoadError(
            requestError instanceof Error
              ? requestError.message
              : 'An unexpected error occurred while loading evidence.',
          )
        }
      } finally {
        if (isActive) {
          setIsLoadingEvidence(false)
        }
      }
    }

    void loadEvidence()

    return () => {
      isActive = false
    }
  }, [selectedIncidentId])

  const filteredIncidents = useMemo(
    () =>
      incidents.filter((incident) => {
        const matchesStatus =
          statusFilter === 'all' || incident.status === statusFilter
        const matchesSeverity =
          severityFilter === 'all' || incident.severity === severityFilter
        const matchesEnvironment =
          environmentFilter === 'all' ||
          incident.environment === environmentFilter

        return matchesStatus && matchesSeverity && matchesEnvironment
      }),
    [incidents, statusFilter, severityFilter, environmentFilter],
  )

  const displayedIncidents = useMemo(
    () =>
      [...filteredIncidents].sort((a, b) => {
        switch (sortOption) {
          case 'newest':
            return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
          case 'oldest':
            return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          case 'severity-high':
            return severityRank[b.severity] - severityRank[a.severity]
          case 'severity-low':
            return severityRank[a.severity] - severityRank[b.severity]
          default:
            return 0
        }
      }),
    [filteredIncidents, sortOption],
  )

  const activeIncidentCount = incidents.filter(
    (incident) => incident.status !== 'resolved',
  ).length
  const criticalIncidentCount = incidents.filter(
    (incident) => incident.severity === 'critical' && incident.status !== 'resolved',
  ).length

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      const response = await fetch(`${API_BASE_URL}/incidents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })

      if (!response.ok) {
        const responseBody = await response.json().catch(() => null)
        const message =
          typeof responseBody?.detail === 'string'
            ? responseBody.detail
            : 'Unable to create incident. Please check the form and try again.'
        throw new Error(message)
      }

      const createdIncident: Incident = await response.json()
      setIncidents((current) => [createdIncident, ...current])
      setForm(emptyForm)
      setIsFormOpen(false)
      setActivePage('incidents')
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : 'An unexpected error occurred.',
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleEvidenceSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (selectedIncidentId === null) return

    setIsSubmittingEvidence(true)
    setEvidenceSubmitError('')

    try {
      const response = await fetch(
        `${API_BASE_URL}/incidents/${selectedIncidentId}/evidence`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(evidenceForm),
        },
      )

      if (!response.ok) {
        let message = 'Unable to add evidence. Please try again.'
        try {
          const errorData = await response.json()
          if (typeof errorData.detail === 'string') {
            message = errorData.detail
          }
        } catch {
          // Keep the default error message.
        }
        throw new Error(message)
      }

      const createdEvidence: IncidentEvidence = await response.json()
      setEvidence((current) => [...current, createdEvidence])
      setEvidenceForm(emptyEvidenceForm)
    } catch (submissionError) {
      setEvidenceSubmitError(
        submissionError instanceof Error
          ? submissionError.message
          : 'An unexpected error occurred while adding evidence.',
      )
    } finally {
      setIsSubmittingEvidence(false)
    }
  }

  async function handleInvestigation() {
    if (selectedIncidentId === null || isInvestigating) return

    setIsInvestigating(true)
    setInvestigationError('')
    setInvestigationResult(null)

    try {
      const response = await fetch(
        `${API_BASE_URL}/incidents/${selectedIncidentId}/investigate`,
        { method: 'POST' },
      )

      if (!response.ok) {
        let message = 'Unable to investigate this incident. Please try again.'
        try {
          const errorData = await response.json()
          if (typeof errorData.detail === 'string') {
            message = errorData.detail
          }
        } catch {
          // Keep the default error message.
        }
        throw new Error(message)
      }

      const result: AIInvestigationResult = await response.json()
      setInvestigationResult(result)
    } catch (requestError) {
      setInvestigationError(
        requestError instanceof Error
          ? requestError.message
          : 'An unexpected error occurred during investigation.',
      )
    } finally {
      setIsInvestigating(false)
    }
  }

  async function handleStatusChange(
    incidentId: number,
    newStatus: Incident['status'],
  ) {
    const currentIncident = incidents.find((incident) => incident.id === incidentId)

    if (
      !currentIncident ||
      currentIncident.status === newStatus ||
      updatingIncidentIds.includes(incidentId)
    ) {
      return
    }

    setStatusUpdateErrors((current) => {
      const next = { ...current }
      delete next[incidentId]
      return next
    })
    setUpdatingIncidentIds((current) => [...current, incidentId])

    try {
      const response = await fetch(`${API_BASE_URL}/incidents/${incidentId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus }),
      })

      if (!response.ok) {
        const responseBody = await response.json().catch(() => null)
        const message =
          typeof responseBody?.detail === 'string'
            ? responseBody.detail
            : 'Unable to update incident status. Please try again.'
        throw new Error(message)
      }

      const updatedIncident: Incident = await response.json()
      setIncidents((current) =>
        current.map((incident) =>
          incident.id === incidentId ? updatedIncident : incident,
        ),
      )
    } catch (statusError) {
      setStatusUpdateErrors((current) => ({
        ...current,
        [incidentId]:
          statusError instanceof Error
            ? statusError.message
            : 'An unexpected error occurred while updating status.',
      }))
    } finally {
      setUpdatingIncidentIds((current) =>
        current.filter((id) => id !== incidentId),
      )
    }
  }

  function closeForm() {
    if (isSubmitting) return
    setIsFormOpen(false)
    setError('')
  }

  function openIncident(incidentId: number) {
    setActivePage('incidents')
    setSelectedIncidentId(incidentId)
  }

  const breadcrumbLabel = selectedIncident
    ? 'Incident details'
    : activePage === 'overview'
      ? 'Overview'
      : 'Incidents'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">O</div>
          <div>
            <div className="brand-name">OpsPilot</div>
            <div className="brand-caption">Incident intelligence</div>
          </div>
        </div>

        <div className="nav-section-label">WORKSPACE</div>

        <nav className="navigation" aria-label="Main navigation">
          {navigationItems.map((item) => (
            <button
              className={`nav-item ${activePage === item.id ? 'active' : ''}`}
              key={item.id}
              type="button"
              aria-current={activePage === item.id ? 'page' : undefined}
              onClick={() => {
                setActivePage(item.id)
                setSelectedIncidentId(null)
                setIsFormOpen(false)
              }}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="status-dot" />
          <span>API workspace</span>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="breadcrumb-divider">/</span>
            <strong>{breadcrumbLabel}</strong>
          </div>
          <div className="topbar-status">
            <span className="status-dot" />
            Incident intelligence
          </div>
        </header>

        <section className="page-content">
          {selectedIncident ? (
            <div className="incident-details">
              <button
                className="secondary-button"
                type="button"
                onClick={() => setSelectedIncidentId(null)}
              >
                ← Back to incidents
              </button>

              <div className="page-heading">
                <div>
                  <p className="eyebrow">
                    INC-{String(selectedIncident.id).padStart(4, '0')}
                  </p>
                  <h1>{selectedIncident.title}</h1>
                  <p className="page-description">
                    Incident details and investigation workspace.
                  </p>
                </div>
                <span className={`severity-badge severity-${selectedIncident.severity}`}>
                  {selectedIncident.severity}
                </span>
              </div>

              <div className="welcome-panel">
                <div>
                  <h2>Incident overview</h2>
                  <p>{selectedIncident.description}</p>
                </div>
              </div>

              <div className="overview-grid">
                <article className="overview-card">
                  <div className="card-label">Affected service</div>
                  <div className="card-placeholder">{selectedIncident.service}</div>
                </article>
                <article className="overview-card">
                  <div className="card-label">Environment</div>
                  <div className="card-placeholder">
                    {selectedIncident.environment ?? 'Unknown'}
                  </div>
                </article>
                <article className="overview-card">
                  <div className="card-label">Current status</div>
                  <div className="card-placeholder">{selectedIncident.status}</div>
                </article>
              </div>

              <div className="section-heading">
                <h2>Add evidence</h2>
                <span>Attach information to this incident</span>
              </div>

              <form className="evidence-form" onSubmit={handleEvidenceSubmit}>
                <div className="form-group">
                  <label htmlFor="evidence-source-type">Evidence type</label>
                  <select
                    id="evidence-source-type"
                    value={evidenceForm.source_type}
                    onChange={(event) =>
                      setEvidenceForm((current) => ({
                        ...current,
                        source_type: event.target.value as EvidenceSourceType,
                      }))
                    }
                  >
                    <option value="log">Log</option>
                    <option value="metric">Metric</option>
                    <option value="trace">Trace</option>
                    <option value="deployment">Deployment</option>
                    <option value="note">Note</option>
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="evidence-content">Evidence content</label>
                  <textarea
                    id="evidence-content"
                    value={evidenceForm.content}
                    onChange={(event) =>
                      setEvidenceForm((current) => ({
                        ...current,
                        content: event.target.value,
                      }))
                    }
                    placeholder="Paste logs, metrics, traces, deployment details, or investigation notes..."
                    rows={5}
                    maxLength={20000}
                    required
                  />
                  <span className="character-count">
                    {evidenceForm.content.length}/20000 characters
                  </span>
                </div>

                {evidenceSubmitError && (
                  <p className="error-message" role="alert">{evidenceSubmitError}</p>
                )}

                <button
                  type="submit"
                  className="primary-button"
                  disabled={isSubmittingEvidence || !evidenceForm.content.trim()}
                >
                  {isSubmittingEvidence ? 'Adding evidence...' : 'Add evidence'}
                </button>
              </form>

              <div className="section-heading">
                <h2>Evidence</h2>
                <span>{evidence.length} records loaded</span>
              </div>

              <section className="evidence-section">
                {isLoadingEvidence ? (
                  <p className="empty-state">Loading evidence...</p>
                ) : evidenceLoadError ? (
                  <p className="error-message" role="alert">{evidenceLoadError}</p>
                ) : evidence.length === 0 ? (
                  <p className="empty-state">
                    No evidence has been added to this incident yet.
                  </p>
                ) : (
                  <div className="evidence-list">
                    {evidence.map((item) => (
                      <article className="evidence-card" key={item.id}>
                        <div className="evidence-card-header">
                          <span className="evidence-source-type">{item.source_type}</span>
                          <span className="evidence-date">{formatDate(item.created_at)}</span>
                        </div>
                        <p className="evidence-content">{item.content}</p>
                      </article>
                    ))}
                  </div>
                )}
              </section>

              <div className="investigation-actions">
                <button
                  type="button"
                  className="primary-button"
                  onClick={handleInvestigation}
                  disabled={isInvestigating || isLoadingEvidence}
                >
                  {isInvestigating ? 'Investigating...' : 'Run AI Investigation'}
                </button>
              </div>

              {investigationError && (
                <p className="error-message" role="alert">{investigationError}</p>
              )}

              {investigationResult && (
                <section className="investigation-results">
                  <div className="section-heading">
                    <h2>AI Investigation Results</h2>
                    <span>Evidence-based analysis</span>
                  </div>

                  <div className="investigation-result-group">
                    <h3>Observed Facts</h3>
                    {investigationResult.observed_facts.length === 0 ? (
                      <p className="empty-state">No confirmed facts identified.</p>
                    ) : (
                      <div className="investigation-list">
                        {investigationResult.observed_facts.map((fact, index) => (
                          <article
                            className="investigation-result-card"
                            key={`${fact.statement}-${index}`}
                          >
                            <p>{fact.statement}</p>
                            <span>Evidence IDs: {fact.evidence_ids.join(', ')}</span>
                          </article>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="investigation-result-group">
                    <h3>Possible Causes</h3>
                    {investigationResult.hypotheses.length === 0 ? (
                      <p className="empty-state">No hypotheses generated.</p>
                    ) : (
                      <div className="investigation-list">
                        {investigationResult.hypotheses.map((hypothesis, index) => (
                          <article
                            className="investigation-result-card"
                            key={`${hypothesis.explanation}-${index}`}
                          >
                            <p>{hypothesis.explanation}</p>
                            <span className={`confidence-badge confidence-${hypothesis.confidence}`}>
                              {hypothesis.confidence.toUpperCase()} confidence
                            </span>
                            <span>
                              Supporting evidence IDs:{' '}
                              {hypothesis.supporting_evidence_ids.length > 0
                                ? hypothesis.supporting_evidence_ids.join(', ')
                                : 'None'}
                            </span>
                          </article>
                        ))}
                      </div>
                    )}
                  </div>

                  <div className="investigation-result-group">
                    <h3>Recommended Checks</h3>
                    {investigationResult.recommended_checks.length === 0 ? (
                      <p className="empty-state">No additional checks recommended.</p>
                    ) : (
                      <ul>
                        {investigationResult.recommended_checks.map((check, index) => (
                          <li key={`${check}-${index}`}>{check}</li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <div className="investigation-result-group">
                    <h3>Unknowns and Evidence Gaps</h3>
                    {investigationResult.unknowns.length === 0 ? (
                      <p className="empty-state">No additional unknowns reported.</p>
                    ) : (
                      <ul>
                        {investigationResult.unknowns.map((unknown, index) => (
                          <li key={`${unknown}-${index}`}>{unknown}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </section>
              )}
            </div>
          ) : activePage === 'overview' ? (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">INCIDENT OPERATIONS</p>
                  <h1>Incident overview</h1>
                  <p className="page-description">
                    Monitor incidents and investigate operational issues with evidence and AI-assisted insights.
                  </p>
                </div>
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => {
                    setError('')
                    setIsFormOpen(true)
                  }}
                >
                  + New incident
                </button>
              </div>

              <div className="welcome-panel">
                <div className="welcome-icon" aria-hidden="true">✦</div>
                <div>
                  <h2>Your incident workspace</h2>
                  <p>
                    Track operational issues, attach evidence, and run AI-assisted investigations from one place.
                  </p>
                </div>
              </div>

              <div className="section-heading">
                <h2>Workspace overview</h2>
                <span>Live incident metrics</span>
              </div>

              <div className="overview-grid">
                <article className="overview-card">
                  <div className="card-label">Total incidents</div>
                  <div className="card-placeholder">
                    {isLoadingIncidents ? '…' : incidents.length}
                  </div>
                  <p>Incidents registered in OpsPilot</p>
                </article>
                <article className="overview-card">
                  <div className="card-label">Active incidents</div>
                  <div className="card-placeholder">
                    {isLoadingIncidents ? '…' : activeIncidentCount}
                  </div>
                  <p>Open or currently being investigated</p>
                </article>
                <article className="overview-card">
                  <div className="card-label">Unresolved critical</div>
                  <div className="card-placeholder">
                    {isLoadingIncidents ? '…' : criticalIncidentCount}
                  </div>
                  <p>Critical incidents not yet resolved</p>
                </article>
              </div>

              {loadError && <p className="form-error" role="alert">{loadError}</p>}

              {isLoadingIncidents && (
                <p className="page-description">Loading incidents...</p>
              )}

              {!isLoadingIncidents && !loadError && incidents.length === 0 && (
                <div className="section-heading">
                  <h2>No incidents yet</h2>
                  <span>Create your first incident to get started.</span>
                </div>
              )}

              {!isLoadingIncidents && incidents.length > 0 && (
                <section className="incident-list-section">
                  <div className="section-heading">
                    <h2>Recent incidents</h2>
                    <button
                      className="secondary-button"
                      type="button"
                      onClick={() => setActivePage('incidents')}
                    >
                      View all incidents
                    </button>
                  </div>
                  <div className="incident-list">
                    {[...incidents]
                      .sort(
                        (a, b) =>
                          new Date(b.created_at).getTime() -
                          new Date(a.created_at).getTime(),
                      )
                      .slice(0, 5)
                      .map((incident) => (
                        <article
                          className="incident-card"
                          key={incident.id}
                          onClick={() => openIncident(incident.id)}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              openIncident(incident.id)
                            }
                          }}
                        >
                          <div className="incident-card-heading">
                            <div>
                              <span className="incident-id">
                                INC-{String(incident.id).padStart(4, '0')}
                              </span>
                              <h3>{incident.title}</h3>
                            </div>
                            <span className={`severity-badge severity-${incident.severity}`}>
                              {incident.severity}
                            </span>
                          </div>
                          <p className="incident-description">{incident.description}</p>
                          <div className="incident-meta">
                            <span>Service: {incident.service}</span>
                            <span>Status: {incident.status}</span>
                            <span>Environment: {incident.environment ?? 'Unknown'}</span>
                          </div>
                        </article>
                      ))}
                  </div>
                </section>
              )}
            </>
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <p className="eyebrow">INCIDENT OPERATIONS</p>
                  <h1>Incidents</h1>
                  <p className="page-description">
                    Browse, filter, prioritize, and update reported incidents.
                  </p>
                </div>
                <button
                  className="primary-button"
                  type="button"
                  onClick={() => {
                    setError('')
                    setIsFormOpen(true)
                  }}
                >
                  + New incident
                </button>
              </div>

              {loadError && <p className="form-error" role="alert">{loadError}</p>}
              {isLoadingIncidents ? (
                <p className="page-description">Loading incidents...</p>
              ) : incidents.length === 0 ? (
                <div className="section-heading">
                  <h2>No incidents yet</h2>
                  <span>Create an incident to get started.</span>
                </div>
              ) : (
                <section className="incident-list-section">
                  <div className="section-heading">
                    <h2>All incidents</h2>
                    <span>{displayedIncidents.length} of {incidents.length} shown</span>
                  </div>

                  <div className="incident-filters">
                    <label>
                      Status
                      <select
                        value={statusFilter}
                        onChange={(event) =>
                          setStatusFilter(event.target.value as IncidentStatusFilter)
                        }
                      >
                        <option value="all">All statuses</option>
                        <option value="open">Open</option>
                        <option value="investigating">Investigating</option>
                        <option value="resolved">Resolved</option>
                      </select>
                    </label>
                    <label>
                      Severity
                      <select
                        value={severityFilter}
                        onChange={(event) =>
                          setSeverityFilter(event.target.value as IncidentSeverityFilter)
                        }
                      >
                        <option value="all">All severities</option>
                        <option value="critical">Critical</option>
                        <option value="high">High</option>
                        <option value="medium">Medium</option>
                        <option value="low">Low</option>
                      </select>
                    </label>
                    <label>
                      Environment
                      <select
                        value={environmentFilter}
                        onChange={(event) =>
                          setEnvironmentFilter(event.target.value as IncidentEnvironmentFilter)
                        }
                      >
                        <option value="all">All environments</option>
                        <option value="production">Production</option>
                        <option value="staging">Staging</option>
                        <option value="development">Development</option>
                      </select>
                    </label>
                    <label>
                      Sort by
                      <select
                        value={sortOption}
                        onChange={(event) =>
                          setSortOption(event.target.value as IncidentSortOption)
                        }
                      >
                        <option value="newest">Newest first</option>
                        <option value="oldest">Oldest first</option>
                        <option value="severity-high">Severity: highest first</option>
                        <option value="severity-low">Severity: lowest first</option>
                      </select>
                    </label>
                  </div>

                  <div className="incident-list">
                    {displayedIncidents.map((incident) => {
                      const isUpdating = updatingIncidentIds.includes(incident.id)

                      return (
                        <article
                          className="incident-card"
                          key={incident.id}
                          onClick={() => openIncident(incident.id)}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              openIncident(incident.id)
                            }
                          }}
                        >
                          <div className="incident-card-heading">
                            <div>
                              <span className="incident-id">
                                INC-{String(incident.id).padStart(4, '0')}
                              </span>
                              <h3>{incident.title}</h3>
                            </div>
                            <span className={`severity-badge severity-${incident.severity}`}>
                              {incident.severity}
                            </span>
                          </div>

                          <p className="incident-description">{incident.description}</p>

                          <div className="incident-meta">
                            <span>Service: {incident.service}</span>
                            <label className="incident-status-control">
                              <span>Status:</span>
                              <select
                                value={incident.status}
                                disabled={isUpdating}
                                onClick={(event) => event.stopPropagation()}
                                onKeyDown={(event) => event.stopPropagation()}
                                onChange={(event) =>
                                  handleStatusChange(
                                    incident.id,
                                    event.target.value as Incident['status'],
                                  )
                                }
                                aria-label={`Status for incident ${incident.id}`}
                              >
                                <option value="open">Open</option>
                                <option value="investigating">Investigating</option>
                                <option value="resolved">Resolved</option>
                              </select>
                              {isUpdating && <span className="status-saving">Saving...</span>}
                            </label>
                            <span>Environment: {incident.environment ?? 'Unknown'}</span>
                          </div>

                          {statusUpdateErrors[incident.id] && (
                            <p className="status-update-error" role="alert">
                              {statusUpdateErrors[incident.id]}
                            </p>
                          )}
                        </article>
                      )
                    })}

                    {displayedIncidents.length === 0 && (
                      <p className="page-description">
                        No incidents match the selected filters.
                      </p>
                    )}
                  </div>
                </section>
              )}
            </>
          )}
        </section>
      </main>

      {isFormOpen && (
        <div className="modal-backdrop" onClick={closeForm}>
          <section
            className="incident-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="incident-form-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-heading">
              <div>
                <p className="eyebrow">INCIDENT OPERATIONS</p>
                <h2 id="incident-form-title">Create an incident</h2>
                <p>Provide the initial details for investigation.</p>
              </div>
              <button
                className="modal-close-button"
                type="button"
                onClick={closeForm}
                disabled={isSubmitting}
                aria-label="Close form"
              >
                ×
              </button>
            </div>

            <form className="incident-form" onSubmit={handleSubmit}>
              <label>
                Incident title
                <input
                  value={form.title}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, title: event.target.value }))
                  }
                  minLength={3}
                  maxLength={150}
                  required
                  placeholder="e.g. Checkout API returning 500 errors"
                />
              </label>

              <label>
                Description
                <textarea
                  value={form.description}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      description: event.target.value,
                    }))
                  }
                  minLength={5}
                  maxLength={2000}
                  required
                  rows={4}
                  placeholder="Describe what is happening and its impact..."
                />
              </label>

              <div className="form-row">
                <label>
                  Affected service
                  <input
                    value={form.service}
                    onChange={(event) =>
                      setForm((current) => ({ ...current, service: event.target.value }))
                    }
                    minLength={2}
                    maxLength={100}
                    required
                    placeholder="e.g. checkout-api"
                  />
                </label>
                <label>
                  Environment
                  <select
                    value={form.environment}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        environment: event.target.value as IncidentForm['environment'],
                      }))
                    }
                    required
                  >
                    <option value="">Select environment</option>
                    <option value="production">Production</option>
                    <option value="staging">Staging</option>
                    <option value="development">Development</option>
                  </select>
                </label>
                <label>
                  Severity
                  <select
                    value={form.severity}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        severity: event.target.value as Incident['severity'],
                      }))
                    }
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </label>
              </div>

              {error && <p className="form-error" role="alert">{error}</p>}

              <div className="form-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={closeForm}
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
                <button className="primary-button" type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Creating...' : 'Create incident'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  )
}

export default App
