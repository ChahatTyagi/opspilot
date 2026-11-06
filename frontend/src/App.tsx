
import { useEffect, useState, type FormEvent } from 'react'
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
  severity: 'low' | 'medium' | 'high' | 'critical'
}

type IncidentStatusFilter = 'all' | Incident['status']
type IncidentSeverityFilter = 'all' | Incident['severity']
type IncidentEnvironmentFilter =
  | 'all'
  | NonNullable<Incident['environment']>

type IncidentSortOption =
  | 'newest'
  | 'oldest'
  | 'severity-high'
  | 'severity-low'

const navigationItems = [
  { label: 'Overview', icon: '▦', active: true },
  { label: 'Incidents', icon: '◉', active: false },
  { label: 'Knowledge Base', icon: '▤', active: false },
]

const emptyForm: IncidentForm = {
  title: '',
  description: '',
  service: '',
  environment: '',
  severity: 'medium',
}

const severityRank: Record<Incident['severity'], number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
}

function App() {
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [form, setForm] = useState<IncidentForm>(emptyForm)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selectedIncidentId, setSelectedIncidentId] =
    useState<number | null>(null)
  const selectedIncident =
    incidents.find((incident) => incident.id === selectedIncidentId) ?? null
  const [isLoadingIncidents, setIsLoadingIncidents] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  const [updatingIncidentIds, setUpdatingIncidentIds] = useState<number[]>([])
  const [statusUpdateErrors, setStatusUpdateErrors] = useState<
    Record<number, string>
  >({})

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
      } catch (loadError) {
        if (isActive) {
          setLoadError(
            loadError instanceof Error
              ? loadError.message
              : 'An unexpected error occurred while loading incidents.',
          )
        }
      } finally {
        if (isActive) {
          setIsLoadingIncidents(false)
        }
      }
    }

    loadIncidents()

    return () => {
      isActive = false
    }
  }, [])

  const filteredIncidents = incidents.filter((incident) => {
    const matchesStatus =
      statusFilter === 'all' || incident.status === statusFilter

    const matchesSeverity =
      severityFilter === 'all' || incident.severity === severityFilter

    const matchesEnvironment =
      environmentFilter === 'all' ||
      incident.environment === environmentFilter

    return matchesStatus && matchesSeverity && matchesEnvironment
  })

  const displayedIncidents = [...filteredIncidents].sort((a, b) => {
    switch (sortOption) {
      case 'newest':
        return (
          new Date(b.created_at).getTime() -
          new Date(a.created_at).getTime()
        )

      case 'oldest':
        return (
          new Date(a.created_at).getTime() -
          new Date(b.created_at).getTime()
        )

      case 'severity-high':
        return severityRank[b.severity] - severityRank[a.severity]

      case 'severity-low':
        return severityRank[a.severity] - severityRank[b.severity]

      default:
        return 0
    }
  })

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      const response = await fetch(`${API_BASE_URL}/incidents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
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

      setIncidents((currentIncidents) => [
        createdIncident,
        ...currentIncidents,
      ])

      setForm(emptyForm)
      setIsFormOpen(false)
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

  async function handleStatusChange(
    incidentId: number,
    newStatus: Incident['status'],
  ) {
    const currentIncident = incidents.find(
      (incident) => incident.id === incidentId,
    )

    if (
      !currentIncident ||
      currentIncident.status === newStatus ||
      updatingIncidentIds.includes(incidentId)
    ) {
      return
    }

    setStatusUpdateErrors((currentErrors) => {
      const updatedErrors = { ...currentErrors }
      delete updatedErrors[incidentId]
      return updatedErrors
    })

    setUpdatingIncidentIds((currentIds) => [...currentIds, incidentId])

    try {
      const response = await fetch(
        `${API_BASE_URL}/incidents/${incidentId}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ status: newStatus }),
        },
      )

      if (!response.ok) {
        const responseBody = await response.json().catch(() => null)

        const message =
          typeof responseBody?.detail === 'string'
            ? responseBody.detail
            : 'Unable to update incident status. Please try again.'

        throw new Error(message)
      }

      const updatedIncident: Incident = await response.json()

      setIncidents((currentIncidents) =>
        currentIncidents.map((incident) =>
          incident.id === incidentId ? updatedIncident : incident,
        ),
      )
    } catch (statusError) {
      setStatusUpdateErrors((currentErrors) => ({
        ...currentErrors,
        [incidentId]:
          statusError instanceof Error
            ? statusError.message
            : 'An unexpected error occurred while updating status.',
      }))
    } finally {
      setUpdatingIncidentIds((currentIds) =>
        currentIds.filter((id) => id !== incidentId),
      )
    }
  }

  function closeForm() {
    if (isSubmitting) return

    setIsFormOpen(false)
    setError('')
  }

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
              className={`nav-item ${item.active ? 'active' : ''}`}
              key={item.label}
              type="button"
            >
              <span className="nav-icon" aria-hidden="true">
                {item.icon}
              </span>
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
            <strong>Overview</strong>
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

                <span
                  className={`severity-badge severity-${selectedIncident.severity}`}
                >
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
                  <div className="card-placeholder">
                    {selectedIncident.service}
                  </div>
                </article>

                <article className="overview-card">
                  <div className="card-label">Environment</div>
                  <div className="card-placeholder">
                    {selectedIncident.environment ?? 'Unknown'}
                  </div>
                </article>

                <article className="overview-card">
                  <div className="card-label">Current status</div>
                  <div className="card-placeholder">
                    {selectedIncident.status}
                  </div>
                </article>
              </div>

              <div className="section-heading">
                <h2>Investigation workspace</h2>
                <span>Next: evidence and AI investigation</span>
              </div>
            </div>
          ) : (
            <>

              <div className="page-heading">
                <div>
                  <p className="eyebrow">INCIDENT OPERATIONS</p>
                  <h1>Good evening</h1>
                  <p className="page-description">
                    Investigate incidents with evidence, context, and AI-assisted
                    insights.
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
                <div className="welcome-icon" aria-hidden="true">
                  ✦
                </div>
                <div>
                  <h2>Your incident workspace</h2>
                  <p>
                    Your dashboard brings incidents, evidence, and investigation
                    reports together in one place.
                  </p>
                </div>
              </div>

              <div className="section-heading">
                <h2>Workspace overview</h2>
                <span>Getting started</span>
              </div>

              <div className="overview-grid">
                <article className="overview-card">
                  <div className="card-label">Incidents</div>
                  <div className="card-placeholder">
                    {isLoadingIncidents ? '…' : incidents.length}
                  </div>
                  <p>Incidents loaded from the backend</p>
                </article>

                <article className="overview-card">
                  <div className="card-label">Investigations</div>
                  <div className="card-placeholder">—</div>
                  <p>AI investigation activity</p>
                </article>

                <article className="overview-card">
                  <div className="card-label">Knowledge sources</div>
                  <div className="card-placeholder">—</div>
                  <p>Runbooks and past incidents</p>
                </article>
              </div>

              {isLoadingIncidents && (
                <p className="page-description">Loading incidents...</p>
              )}

              {loadError && <p className="form-error">{loadError}</p>}

              {!isLoadingIncidents && !loadError && incidents.length === 0 && (
                <div className="section-heading">
                  <h2>No incidents yet</h2>
                  <span>Create an incident to get started</span>
                </div>
              )}

              {incidents.length > 0 && (
                <section className="incident-list-section">
                  <div className="section-heading">
                    <h2>Incidents</h2>
                    <span>
                      {displayedIncidents.length} of {incidents.length} shown
                    </span>
                  </div>

                  <div className="incident-filters">
                    <label>
                      Status
                      <select
                        value={statusFilter}
                        onChange={(event) =>
                          setStatusFilter(
                            event.target.value as IncidentStatusFilter,
                          )
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
                          setSeverityFilter(
                            event.target.value as IncidentSeverityFilter,
                          )
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
                          setEnvironmentFilter(
                            event.target.value as IncidentEnvironmentFilter,
                          )
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
                        <option value="severity-high">
                          Severity: highest first
                        </option>
                        <option value="severity-low">
                          Severity: lowest first
                        </option>
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
                          onClick={() => setSelectedIncidentId(incident.id)}
                          role="button"
                          tabIndex={0}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' || event.key === ' ') {
                              event.preventDefault()
                              setSelectedIncidentId(incident.id)
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

                            <span
                              className={`severity-badge severity-${incident.severity}`}
                            >
                              {incident.severity}
                            </span>
                          </div>

                          <p className="incident-description">
                            {incident.description}
                          </p>

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
                                <option value="investigating">
                                  Investigating
                                </option>
                                <option value="resolved">Resolved</option>
                              </select>

                              {isUpdating && (
                                <span className="status-saving">Saving...</span>
                              )}
                            </label>

                            <span>
                              Environment: {incident.environment ?? 'Unknown'}
                            </span>
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
      </main >

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
                    setForm({ ...form, title: event.target.value })
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
                    setForm({ ...form, description: event.target.value })
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
                      setForm({ ...form, service: event.target.value })
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
                      setForm({
                        ...form,
                        environment:
                          event.target.value as IncidentForm['environment'],
                      })
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
                      setForm({
                        ...form,
                        severity:
                          event.target.value as IncidentForm['severity'],
                      })
                    }
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </label>
              </div>

              {error && <p className="form-error">{error}</p>}

              <div className="form-actions">
                <button
                  className="secondary-button"
                  type="button"
                  onClick={closeForm}
                  disabled={isSubmitting}
                >
                  Cancel
                </button>

                <button
                  className="primary-button"
                  type="submit"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? 'Creating...' : 'Create incident'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )
      }
    </div >
  )
}

export default App
