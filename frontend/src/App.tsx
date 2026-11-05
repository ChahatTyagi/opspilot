import { useEffect, useState } from 'react'
import './App.css'

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

function App() {
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [form, setForm] = useState<IncidentForm>(emptyForm)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [isLoadingIncidents, setIsLoadingIncidents] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    async function loadIncidents() {
      setLoadError('')

      try {
        const response = await fetch('/api/incidents')

        if (!response.ok) {
          throw new Error('Unable to load incidents. Please try again.')
        }

        const loadedIncidents: Incident[] = await response.json()
        setIncidents(loadedIncidents)
      } catch (loadError) {
        setLoadError(
          loadError instanceof Error
            ? loadError.message
            : 'An unexpected error occurred while loading incidents.',
        )
      } finally {
        setIsLoadingIncidents(false)
      }
    }

    loadIncidents()
  }, [])

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    setIsSubmitting(true)

    try {
      const response = await fetch('/api/incidents', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          ...form,
          environment: form.environment || null,
        }),
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
                <span>{incidents.length} loaded</span>
              </div>

              <div className="incident-list">
                {incidents.map((incident) => (
                  <article className="incident-card" key={incident.id}>
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
                      <span>Status: {incident.status}</span>
                      {incident.environment && (
                        <span>Environment: {incident.environment}</span>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </section>
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

              <div className="form-row">
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
                  >
                    <option value="">Not specified</option>
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
                  {isSubmitting ? 'Creating…' : 'Create incident'}
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