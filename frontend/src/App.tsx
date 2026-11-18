
import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from 'react'

import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock3,
  Command,
  FileText,
  Filter,
  Gauge,
  Layers3,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  GitBranch,
  CalendarClock,
  Server,
  ShieldAlert,
  Sparkles,
  Terminal,
  X,
  Zap,
} from 'lucide-react'

import './App.css'

import {
  createIncident,
  createIncidentEvidence,
  getIncidents,
  getIncidentEvidence,
  getInvestigationHistory,
  runIncidentInvestigation,
  updateIncidentStatus,
  type Incident,
  type IncidentForm,
  type IncidentEvidence,
  type EvidenceForm,
  type EvidenceSourceType,
  type AIInvestigationResult,
  type InvestigationHistoryRecord,
} from './services/api'

type WorkspacePage = 'overview' | 'incidents' | 'investigator' | 'evidence'
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
  {
    id: 'overview' as const,
    label: 'Overview',
    icon: Gauge,
  },
  {
    id: 'incidents' as const,
    label: 'Incidents',
    icon: AlertTriangle,
  },
]

const platformNavigationItems = [
  {
    id: 'investigator' as const,
    label: 'AI Investigator',
    description: 'Evidence-based analysis',
    icon: Bot,
  },
  {
    id: 'evidence' as const,
    label: 'Evidence',
    description: 'Logs, metrics and traces',
    icon: FileText,
  },
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

function formatRelativeDate(value: string) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return 'Unknown date'
  }

  const difference = Date.now() - date.getTime()
  const minutes = Math.floor(difference / 60000)

  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.floor(minutes / 60)

  if (hours < 24) return `${hours}h ago`

  const days = Math.floor(hours / 24)

  if (days < 7) return `${days}d ago`

  return date.toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

function getErrorMessage(
  error: unknown,
  fallback: string,
): string {
  return error instanceof Error ? error.message : fallback
}

function getIncidentReference(id: number) {
  return `INC-${String(id).padStart(4, '0')}`
}

function SeverityBadge({
  severity,
}: {
  severity: Incident['severity']
}) {
  return (
    <span className={`severity-badge severity-${severity}`}>
      <span className="severity-indicator" />
      {severity}
    </span>
  )
}

function StatusBadge({
  status,
}: {
  status: Incident['status']
}) {
  return (
    <span className={`status-badge status-${status}`}>
      <span className="status-indicator" />
      {status}
    </span>
  )
}

function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof FileText
  title: string
  description: string
}) {
  return (
    <div className="empty-state-panel">
      <div className="empty-state-icon">
        <Icon size={22} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  )
}

type RelationshipGraphProps = {
  result: AIInvestigationResult
  evidence: IncidentEvidence[]
}

function EvidenceRelationshipGraph({
  result,
  evidence,
}: RelationshipGraphProps) {
  const evidenceById = new Map(
    evidence.map((item) => [String(item.id), item]),
  )

  const findings = [
    ...result.observed_facts.map((fact, index) => ({
      id: `fact-${index}`,
      label: fact.statement,
      kind: 'Observed fact',
      evidenceIds: fact.evidence_ids.map(String),
    })),
    ...result.hypotheses.map((hypothesis, index) => ({
      id: `hypothesis-${index}`,
      label: hypothesis.explanation,
      kind: `${hypothesis.confidence} confidence hypothesis`,
      evidenceIds: hypothesis.supporting_evidence_ids.map(String),
    })),
  ]

  const linkedEvidenceIds = Array.from(
    new Set(findings.flatMap((finding) => finding.evidenceIds)),
  )

  if (findings.length === 0) {
    return (
      <div className="insight-empty-note">
        Relationship mapping will appear when the investigation returns facts or hypotheses.
      </div>
    )
  }

  return (
    <section className="content-panel relationship-panel">
      <div className="panel-heading">
        <div>
          <div className="panel-title-row">
            <GitBranch size={18} />
            <h2>Evidence relationship map</h2>
          </div>
          <p>Trace each AI finding back to the evidence records that support it.</p>
        </div>
        <span className="provenance-label">Evidence provenance</span>
      </div>
      <div className="relationship-legend">
        <span><i className="legend-dot legend-fact" /> Observed fact</span>
        <span><i className="legend-dot legend-hypothesis" /> Hypothesis</span>
        <span><i className="legend-dot legend-evidence" /> Evidence record</span>
      </div>
      <div className="relationship-graph">
        <div className="relationship-column relationship-findings">
          <div className="relationship-column-title">AI findings <span>{findings.length}</span></div>
          {findings.map((finding) => (
            <article className={`relationship-node ${finding.kind.startsWith('Observed') ? 'node-fact' : 'node-hypothesis'}`} key={finding.id}>
              <span className="relationship-node-kind">{finding.kind}</span>
              <p>{finding.label}</p>
              <div className="relationship-links">
                {finding.evidenceIds.length === 0 ? (
                  <span className="unlinked-label">No evidence linked</span>
                ) : finding.evidenceIds.map((id) => (
                  <span key={id}>Evidence #{id}</span>
                ))}
              </div>
            </article>
          ))}
        </div>
        <div className="relationship-column relationship-sources">
          <div className="relationship-column-title">Source evidence <span>{linkedEvidenceIds.length}</span></div>
          {linkedEvidenceIds.length === 0 ? (
            <div className="relationship-source-empty">No evidence references were returned.</div>
          ) : linkedEvidenceIds.map((id) => {
            const item = evidenceById.get(id)
            return (
              <div className="relationship-source-node" key={id}>
                <span className="source-node-icon"><FileText size={15} /></span>
                <span className="source-node-copy">
                  <strong>Evidence #{id}</strong>
                  <small>{item ? `${item.source_type} · ${formatRelativeDate(item.created_at)}` : 'Referenced record unavailable in current evidence list'}</small>
                </span>
                <ArrowUpRight size={14} />
              </div>
            )
          })}
        </div>
      </div>
      <p className="provenance-footnote">A linked record indicates the evidence ID cited by the model; it does not independently prove a hypothesis.</p>
    </section>
  )
}

function App() {
  const [activePage, setActivePage] =
    useState<WorkspacePage>('overview')

  const [isFormOpen, setIsFormOpen] = useState(false)
  const [form, setForm] = useState<IncidentForm>(emptyForm)

  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selectedIncidentId, setSelectedIncidentId] =
    useState<number | null>(null)

  const selectedIncident =
    incidents.find(
      (incident) => incident.id === selectedIncidentId,
    ) ?? null

  const [isLoadingIncidents, setIsLoadingIncidents] =
    useState(true)
  const [loadError, setLoadError] = useState('')

  const [evidence, setEvidence] =
    useState<IncidentEvidence[]>([])
  const [isLoadingEvidence, setIsLoadingEvidence] =
    useState(false)
  const [evidenceLoadError, setEvidenceLoadError] =
    useState('')
  const [evidenceForm, setEvidenceForm] =
    useState<EvidenceForm>(emptyEvidenceForm)
  const [isSubmittingEvidence, setIsSubmittingEvidence] =
    useState(false)
  const [evidenceSubmitError, setEvidenceSubmitError] =
    useState('')

  const [evidenceSearch, setEvidenceSearch] = useState('')
  const [evidenceTypeFilter, setEvidenceTypeFilter] =
    useState<EvidenceSourceType | 'all'>('all')

  const [investigationResult, setInvestigationResult] =
    useState<AIInvestigationResult | null>(null)

  const [investigationHistory, setInvestigationHistory] =
    useState<InvestigationHistoryRecord[]>([])

  const [
    isLoadingInvestigationHistory,
    setIsLoadingInvestigationHistory,
  ] = useState(false)

  const [isInvestigating, setIsInvestigating] =
    useState(false)

  const [investigationError, setInvestigationError] =
    useState('')

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState('')

  const [updatingIncidentIds, setUpdatingIncidentIds] =
    useState<number[]>([])

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

  const [searchQuery, setSearchQuery] = useState('')

  // Load incidents when the application starts.
  useEffect(() => {
    let isActive = true

    async function loadIncidents() {
      setLoadError('')
      setIsLoadingIncidents(true)

      try {
        const loadedIncidents = await getIncidents()

        if (isActive) {
          setIncidents(loadedIncidents)
        }
      } catch (requestError) {
        if (isActive) {
          setLoadError(
            getErrorMessage(
              requestError,
              'Unable to load incidents.',
            ),
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

  // Load evidence when the selected incident changes.
  useEffect(() => {
    if (selectedIncidentId === null) {
      setEvidence([])
      setEvidenceLoadError('')
      setIsLoadingEvidence(false)
      return
    }

    const incidentId = selectedIncidentId
    let isActive = true

    async function loadEvidence() {
      setEvidence([])
      setEvidenceLoadError('')
      setIsLoadingEvidence(true)

      try {
        const loadedEvidence =
          await getIncidentEvidence(incidentId)

        if (isActive) {
          setEvidence(loadedEvidence)
        }
      } catch (requestError) {
        if (isActive) {
          setEvidenceLoadError(
            getErrorMessage(
              requestError,
              'Unable to load incident evidence.',
            ),
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

  // Load persisted investigation history.
  useEffect(() => {
    if (selectedIncidentId === null) {
      setInvestigationHistory([])
      setInvestigationResult(null)
      setIsLoadingInvestigationHistory(false)
      setInvestigationError('')
      return
    }

    const incidentId = selectedIncidentId
    let isActive = true

    async function loadInvestigationHistory() {
      setInvestigationHistory([])
      setInvestigationResult(null)
      setInvestigationError('')
      setIsLoadingInvestigationHistory(true)

      try {
        const history =
          await getInvestigationHistory(incidentId)

        if (isActive) {
          setInvestigationHistory(history)
          setInvestigationResult(history[0]?.result ?? null)
        }
      } catch (requestError) {
        if (isActive) {
          setInvestigationError(
            getErrorMessage(
              requestError,
              'Unable to load investigation history.',
            ),
          )
        }
      } finally {
        if (isActive) {
          setIsLoadingInvestigationHistory(false)
        }
      }
    }

    void loadInvestigationHistory()

    return () => {
      isActive = false
    }
  }, [selectedIncidentId])

  // Filter incidents.
  const filteredIncidents = useMemo(
    () =>
      incidents.filter((incident) => {
        const matchesStatus =
          statusFilter === 'all' ||
          incident.status === statusFilter

        const matchesSeverity =
          severityFilter === 'all' ||
          incident.severity === severityFilter

        const matchesEnvironment =
          environmentFilter === 'all' ||
          incident.environment === environmentFilter

        const normalizedSearch = searchQuery
          .trim()
          .toLowerCase()

        const matchesSearch =
          !normalizedSearch ||
          [
            incident.title,
            incident.description,
            incident.service,
            incident.environment ?? '',
            getIncidentReference(incident.id),
          ].some((value) =>
            value.toLowerCase().includes(normalizedSearch),
          )

        return (
          matchesStatus &&
          matchesSeverity &&
          matchesEnvironment &&
          matchesSearch
        )
      }),
    [
      incidents,
      statusFilter,
      severityFilter,
      environmentFilter,
      searchQuery,
    ],
  )

  // Sort incidents without mutating the original array.
  const displayedIncidents = useMemo(
    () =>
      [...filteredIncidents].sort((a, b) => {
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
            return (
              severityRank[b.severity] -
              severityRank[a.severity]
            )

          case 'severity-low':
            return (
              severityRank[a.severity] -
              severityRank[b.severity]
            )

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
    (incident) =>
      incident.severity === 'critical' &&
      incident.status !== 'resolved',
  ).length

  const resolvedIncidentCount = incidents.filter(
    (incident) => incident.status === 'resolved',
  ).length

  const highPriorityCount = incidents.filter(
    (incident) =>
      (incident.severity === 'critical' ||
        incident.severity === 'high') &&
      incident.status !== 'resolved',
  ).length

  const recentIncidents = useMemo(
    () =>
      [...incidents]
        .sort(
          (a, b) =>
            new Date(b.created_at).getTime() -
            new Date(a.created_at).getTime(),
        )
        .slice(0, 5),
    [incidents],
  )

  const filteredEvidence = useMemo(() => {
    const normalizedQuery = evidenceSearch.trim().toLowerCase()

    return [...evidence]
      .filter((item) =>
        evidenceTypeFilter === 'all' || item.source_type === evidenceTypeFilter,
      )
      .filter((item) =>
        !normalizedQuery ||
        [item.content, item.source_type, String(item.id)]
          .some((value) => value.toLowerCase().includes(normalizedQuery)),
      )
      .sort((a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      )
  }, [evidence, evidenceSearch, evidenceTypeFilter])

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    if (isSubmitting) return

    setError('')
    setIsSubmitting(true)

    try {
      const createdIncident = await createIncident(form)

      setIncidents((current) => [
        createdIncident,
        ...current,
      ])

      setForm(emptyForm)
      setIsFormOpen(false)
      setActivePage('incidents')
      setSelectedIncidentId(null)
    } catch (submissionError) {
      setError(
        getErrorMessage(
          submissionError,
          'Unable to create incident.',
        ),
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleEvidenceSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    if (
      selectedIncidentId === null ||
      isSubmittingEvidence ||
      !evidenceForm.content.trim()
    ) {
      return
    }

    const incidentId = selectedIncidentId

    setIsSubmittingEvidence(true)
    setEvidenceSubmitError('')

    try {
      const createdEvidence =
        await createIncidentEvidence(
          incidentId,
          evidenceForm,
        )

      if (selectedIncidentId === incidentId) {
        setEvidence((current) => [
          ...current,
          createdEvidence,
        ])

        setEvidenceForm(emptyEvidenceForm)
      }
    } catch (submissionError) {
      setEvidenceSubmitError(
        getErrorMessage(
          submissionError,
          'Unable to add evidence.',
        ),
      )
    } finally {
      setIsSubmittingEvidence(false)
    }
  }

  // Run an AI investigation and refresh persisted history.
  async function handleInvestigation() {
    if (
      selectedIncidentId === null ||
      isInvestigating
    ) {
      return
    }

    const incidentId = selectedIncidentId

    setIsInvestigating(true)
    setInvestigationError('')
    setInvestigationResult(null)

    try {
      const result =
        await runIncidentInvestigation(incidentId)

      if (selectedIncidentId === incidentId) {
        setInvestigationResult(result)
      }

      try {
        const history =
          await getInvestigationHistory(incidentId)

        if (selectedIncidentId === incidentId) {
          setInvestigationHistory(history)
          setInvestigationResult(
            history[0]?.result ?? result,
          )
        }
      } catch {
        // Keep the successfully returned investigation.
      }
    } catch (requestError) {
      if (selectedIncidentId === incidentId) {
        setInvestigationError(
          getErrorMessage(
            requestError,
            'Investigation could not be completed.',
          ),
        )
      }
    } finally {
      setIsInvestigating(false)
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

    setStatusUpdateErrors((current) => {
      const next = { ...current }
      delete next[incidentId]
      return next
    })

    setUpdatingIncidentIds((current) => [
      ...current,
      incidentId,
    ])

    try {
      const updatedIncident =
        await updateIncidentStatus(
          incidentId,
          newStatus,
        )

      setIncidents((current) =>
        current.map((incident) =>
          incident.id === incidentId
            ? updatedIncident
            : incident,
        ),
      )
    } catch (statusError) {
      setStatusUpdateErrors((current) => ({
        ...current,
        [incidentId]: getErrorMessage(
          statusError,
          'Unable to update incident status.',
        ),
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

  function navigateTo(page: WorkspacePage) {
    setActivePage(page)

    // Keep the current incident selected when moving between
    // its investigation and evidence workspaces.
    if (page === 'overview' || page === 'incidents') {
      setSelectedIncidentId(null)
    }

    setIsFormOpen(false)
  }

  function resetFilters() {
    setStatusFilter('all')
    setSeverityFilter('all')
    setEnvironmentFilter('all')
    setSortOption('newest')
    setSearchQuery('')
  }

  const breadcrumbLabel =
    activePage === 'investigator'
      ? 'AI Investigator'
      : activePage === 'evidence'
        ? 'Evidence'
        : selectedIncident && activePage === 'incidents'
          ? 'Incident details'
          : activePage === 'overview'
            ? 'Overview'
            : 'Incidents'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Activity size={23} strokeWidth={2.5} />
          </div>

          <div className="brand-copy">
            <div className="brand-name">OpsPilot</div>
            <div className="brand-caption">
              INCIDENT INTELLIGENCE
            </div>
          </div>
        </div>

        <div className="sidebar-workspace">
          <span className="workspace-avatar">O</span>
          <span className="workspace-copy">
            <strong>Operations</strong>
            <small>Workspace</small>
          </span>
          <ChevronDown size={15} />
        </div>

        <div className="nav-section-label">
          WORKSPACE
        </div>

        <nav
          className="navigation"
          aria-label="Main navigation"
        >
          {navigationItems.map((item) => {
            const Icon = item.icon

            return (
              <button
                className={`nav-item ${
                  activePage === item.id
                    ? 'active'
                    : ''
                }`}
                key={item.id}
                type="button"
                aria-current={
                  activePage === item.id
                    ? 'page'
                    : undefined
                }
                onClick={() => navigateTo(item.id)}
              >
                <Icon size={18} strokeWidth={1.9} />
                <span>{item.label}</span>

                {item.id === 'incidents' &&
                  incidents.length > 0 && (
                    <span className="nav-count">
                      {incidents.length}
                    </span>
                  )}
              </button>
            )
          })}
        </nav>

        <div className="sidebar-divider" />

        <div className="nav-section-label">
          PLATFORM
        </div>

        <nav className="navigation platform-navigation" aria-label="Platform tools">
          {platformNavigationItems.map((item) => {
            const Icon = item.icon
            const isActive = activePage === item.id

            return (
              <button
                className={`nav-item ${isActive ? 'active' : ''}`}
                key={item.id}
                type="button"
                aria-current={isActive ? 'page' : undefined}
                onClick={() => navigateTo(item.id)}
              >
                <Icon size={18} strokeWidth={1.9} />
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>

        <div className="sidebar-spacer" />

        <div className="sidebar-system-card">
          <div className="system-card-heading">
            <span className="system-online-dot" />
            System status
          </div>
          <p>Workspace connected</p>
          <span className="system-card-caption">
            API workspace
          </span>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-footer-mark">O</div>
          <div>
            <strong>OpsPilot</strong>
            <span>Incident workspace</span>
          </div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <div className="breadcrumb">
              <span>Workspace</span>
              <ChevronRight size={14} />
              <strong>{breadcrumbLabel}</strong>
            </div>
          </div>

          <div className="topbar-right">
            <div className="topbar-system-status">
              <span className="system-online-dot" />
              <span>Workspace connected</span>
            </div>

            <div className="topbar-divider" />

            <div className="topbar-product-mark">
              <Command size={17} />
            </div>
          </div>
        </header>

        <section className="page-content">
          {activePage === 'incidents' && selectedIncident ? (
            <div className="incident-details">
              <button
                className="back-link"
                type="button"
                onClick={() =>
                  setSelectedIncidentId(null)
                }
              >
                <ArrowLeft size={16} />
                Back to incidents
              </button>

              <div className="detail-page-heading">
                <div className="detail-heading-main">
                  <div className="eyebrow">
                    {getIncidentReference(selectedIncident.id)}
                    <span className="eyebrow-divider">/</span>
                    INCIDENT DETAILS
                  </div>

                  <h1>{selectedIncident.title}</h1>

                  <p className="page-description">
                    Review incident information, supporting
                    evidence, and AI-generated investigation
                    findings.
                  </p>

                  <div className="detail-heading-badges">
                    <SeverityBadge
                      severity={selectedIncident.severity}
                    />
                    <StatusBadge
                      status={selectedIncident.status}
                    />
                  </div>
                </div>

                <div className="detail-heading-action">
                  <button
                    className="secondary-button"
                    type="button"
                    onClick={handleInvestigation}
                    disabled={
                      isInvestigating ||
                      isLoadingEvidence ||
                      isLoadingInvestigationHistory
                    }
                  >
                    {isInvestigating ? (
                      <LoaderCircle
                        size={16}
                        className="spin-icon"
                      />
                    ) : (
                      <Sparkles size={16} />
                    )}
                    {isInvestigating
                      ? 'Investigating'
                      : 'Run investigation'}
                  </button>
                </div>
              </div>

              <div className="detail-overview-panel">
                <div className="detail-panel-heading">
                  <div className="detail-panel-icon">
                    <AlertCircle size={18} />
                  </div>
                  <div>
                    <h2>Incident summary</h2>
                    <p>
                      Initial report and affected system
                    </p>
                  </div>
                </div>

                <p className="detail-description">
                  {selectedIncident.description}
                </p>

                <div className="detail-metadata-grid">
                  <div className="detail-metadata-item">
                    <span className="metadata-label">
                      <Server size={14} />
                      Affected service
                    </span>
                    <strong>{selectedIncident.service}</strong>
                  </div>

                  <div className="detail-metadata-item">
                    <span className="metadata-label">
                      <Layers3 size={14} />
                      Environment
                    </span>
                    <strong>
                      {selectedIncident.environment ?? 'Unknown'}
                    </strong>
                  </div>

                  <div className="detail-metadata-item">
                    <span className="metadata-label">
                      <Clock3 size={14} />
                      Reported
                    </span>
                    <strong>
                      {formatDate(selectedIncident.created_at)}
                    </strong>
                  </div>
                </div>
              </div>

              <div className="detail-content-grid">
                <div className="detail-main-column">
                  <section className="content-panel">
                    <div className="panel-heading">
                      <div>
                        <div className="panel-title-row">
                          <FileText size={18} />
                          <h2>Evidence</h2>
                          <span className="count-badge">
                            {evidence.length}
                          </span>
                        </div>
                        <p>
                          Supporting logs, metrics, traces,
                          and operational notes.
                        </p>
                      </div>
                    </div>

                    <form
                      className="evidence-form"
                      onSubmit={handleEvidenceSubmit}
                    >
                      <div className="form-group">
                        <label htmlFor="evidence-source-type">
                          Evidence type
                        </label>

                        <select
                          id="evidence-source-type"
                          value={evidenceForm.source_type}
                          onChange={(event) =>
                            setEvidenceForm((current) => ({
                              ...current,
                              source_type: event.target
                                .value as EvidenceSourceType,
                            }))
                          }
                        >
                          <option value="log">Log</option>
                          <option value="metric">Metric</option>
                          <option value="trace">Trace</option>
                          <option value="deployment">
                            Deployment
                          </option>
                          <option value="note">Note</option>
                        </select>
                      </div>

                      <div className="form-group">
                        <label htmlFor="evidence-content">
                          Evidence content
                        </label>

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
                          {evidenceForm.content.length.toLocaleString()}
                          {' '}/ 20,000 characters
                        </span>
                      </div>

                      {evidenceSubmitError && (
                        <p
                          className="error-message"
                          role="alert"
                        >
                          {evidenceSubmitError}
                        </p>
                      )}

                      <div className="form-actions">
                        <button
                          className="primary-button"
                          type="submit"
                          disabled={
                            isSubmittingEvidence ||
                            !evidenceForm.content.trim()
                          }
                        >
                          {isSubmittingEvidence ? (
                            <LoaderCircle
                              size={16}
                              className="spin-icon"
                            />
                          ) : (
                            <Plus size={16} />
                          )}
                          {isSubmittingEvidence
                            ? 'Adding evidence...'
                            : 'Add evidence'}
                        </button>
                      </div>
                    </form>

                    <div className="panel-divider" />

                    {isLoadingEvidence ? (
                      <div className="loading-state">
                        <LoaderCircle
                          size={19}
                          className="spin-icon"
                        />
                        Loading evidence...
                      </div>
                    ) : evidenceLoadError ? (
                      <p
                        className="error-message"
                        role="alert"
                      >
                        {evidenceLoadError}
                      </p>
                    ) : evidence.length === 0 ? (
                      <EmptyState
                        icon={FileText}
                        title="No evidence added"
                        description="Add logs, metrics, traces, or notes to give the AI investigator more context."
                      />
                    ) : (
                      <div className="evidence-list">
                        {evidence.map((item) => (
                          <article
                            className="evidence-card"
                            key={item.id}
                          >
                            <div className="evidence-card-header">
                              <div className="evidence-type">
                                <Terminal size={15} />
                                <span>
                                  {item.source_type}
                                </span>
                              </div>

                              <span className="evidence-date">
                                {formatRelativeDate(item.created_at)}
                              </span>
                            </div>

                            <pre className="evidence-content">
                              {item.content}
                            </pre>

                            <div className="evidence-card-footer">
                              <span>
                                Evidence #{item.id}
                              </span>
                              <span>
                                {formatDate(item.created_at)}
                              </span>
                            </div>
                          </article>
                        ))}
                      </div>
                    )}
                  </section>

                  <section className="content-panel investigation-panel">
                    <div className="panel-heading">
                      <div>
                        <div className="panel-title-row">
                          <Sparkles size={19} />
                          <h2>AI investigation</h2>
                        </div>
                        <p>
                          Evidence-grounded analysis of this
                          incident.
                        </p>
                      </div>

                      <button
                        className="primary-button"
                        type="button"
                        onClick={handleInvestigation}
                        disabled={
                          isInvestigating ||
                          isLoadingEvidence ||
                          isLoadingInvestigationHistory
                        }
                      >
                        {isInvestigating ? (
                          <LoaderCircle
                            size={16}
                            className="spin-icon"
                          />
                        ) : (
                          <Zap size={16} />
                        )}
                        {isInvestigating
                          ? 'Analyzing...'
                          : 'Run analysis'}
                      </button>
                    </div>

                    {investigationError && (
                      <p
                        className="error-message"
                        role="alert"
                      >
                        {investigationError}
                      </p>
                    )}

                    {isInvestigating && (
                      <div className="investigation-progress">
                        <div className="investigation-progress-icon">
                          <Sparkles size={19} />
                        </div>
                        <div>
                          <strong>
                            Investigating incident
                          </strong>
                          <p>
                            Reviewing evidence and generating
                            an evidence-based analysis. This
                            may take a little while.
                          </p>
                        </div>
                      </div>
                    )}

                    {isLoadingInvestigationHistory && (
                      <div className="loading-state">
                        <LoaderCircle
                          size={18}
                          className="spin-icon"
                        />
                        Loading saved investigations...
                      </div>
                    )}

                    {!isLoadingInvestigationHistory &&
                      investigationHistory.length > 0 && (
                        <div className="history-summary">
                          <Clock3 size={15} />
                          <span>
                            {investigationHistory.length} saved
                            investigation
                            {investigationHistory.length === 1
                              ? ''
                              : 's'}
                          </span>
                          <span className="history-separator">
                            ·
                          </span>
                          <span>
                            Latest:{' '}
                            {formatDate(
                              investigationHistory[0].created_at,
                            )}
                          </span>
                        </div>
                      )}

                    {!isLoadingInvestigationHistory &&
                      !isInvestigating &&
                      !investigationError &&
                      investigationHistory.length === 0 &&
                      !investigationResult && (
                        <EmptyState
                          icon={Bot}
                          title="Ready to investigate"
                          description="Run an AI investigation to identify observed facts, possible causes, recommended checks, and evidence gaps."
                        />
                      )}

                    {investigationResult && (
                      <div className="investigation-results">
                        <div className="investigation-result-banner">
                          <div className="result-banner-icon">
                            <CheckCircle2 size={18} />
                          </div>
                          <div>
                            <strong>
                              Investigation completed
                            </strong>
                            <p>
                              Review the findings and their
                              supporting evidence below.
                            </p>
                          </div>
                        </div>

                        <section className="investigation-result-group">
                          <div className="result-group-heading">
                            <div className="result-group-icon facts-icon">
                              <CheckCircle2 size={17} />
                            </div>
                            <div>
                              <h3>Observed facts</h3>
                              <p>
                                Findings supported by evidence
                              </p>
                            </div>
                            <span className="count-badge">
                              {investigationResult.observed_facts.length}
                            </span>
                          </div>

                          {investigationResult.observed_facts.length ===
                          0 ? (
                            <p className="empty-state">
                              No confirmed facts identified.
                            </p>
                          ) : (
                            <div className="investigation-list">
                              {investigationResult.observed_facts.map(
                                (fact, index) => (
                                  <article
                                    className="investigation-result-card"
                                    key={`${fact.statement}-${index}`}
                                  >
                                    <p>{fact.statement}</p>
                                    <div className="evidence-reference">
                                      <FileText size={13} />
                                      Evidence IDs:{' '}
                                      {fact.evidence_ids.join(', ')}
                                    </div>
                                  </article>
                                ),
                              )}
                            </div>
                          )}
                        </section>

                        <section className="investigation-result-group">
                          <div className="result-group-heading">
                            <div className="result-group-icon hypotheses-icon">
                              <LightbulbIcon />
                            </div>
                            <div>
                              <h3>Possible causes</h3>
                              <p>
                                Hypotheses requiring validation
                              </p>
                            </div>
                            <span className="count-badge">
                              {investigationResult.hypotheses.length}
                            </span>
                          </div>

                          {investigationResult.hypotheses.length ===
                          0 ? (
                            <p className="empty-state">
                              No hypotheses generated.
                            </p>
                          ) : (
                            <div className="investigation-list">
                              {investigationResult.hypotheses.map(
                                (hypothesis, index) => (
                                  <article
                                    className="investigation-result-card"
                                    key={`${hypothesis.explanation}-${index}`}
                                  >
                                    <p>
                                      {hypothesis.explanation}
                                    </p>

                                    <span
                                      className={`confidence-badge confidence-${hypothesis.confidence}`}
                                    >
                                      {hypothesis.confidence.toUpperCase()}
                                      {' '}confidence
                                    </span>

                                    <div className="evidence-reference">
                                      <FileText size={13} />
                                      Supporting evidence:{' '}
                                      {hypothesis.supporting_evidence_ids
                                        .length > 0
                                        ? hypothesis.supporting_evidence_ids.join(
                                            ', ',
                                          )
                                        : 'None'}
                                    </div>
                                  </article>
                                ),
                              )}
                            </div>
                          )}
                        </section>

                        <section className="investigation-result-group">
                          <div className="result-group-heading">
                            <div className="result-group-icon checks-icon">
                              <ShieldAlert size={17} />
                            </div>
                            <div>
                              <h3>Recommended checks</h3>
                              <p>
                                Suggested next investigation steps
                              </p>
                            </div>
                          </div>

                          {investigationResult.recommended_checks.length ===
                          0 ? (
                            <p className="empty-state">
                              No additional checks recommended.
                            </p>
                          ) : (
                            <ul className="recommendation-list">
                              {investigationResult.recommended_checks.map(
                                (check, index) => (
                                  <li key={`${check}-${index}`}>
                                    <span className="recommendation-number">
                                      {index + 1}
                                    </span>
                                    {check}
                                  </li>
                                ),
                              )}
                            </ul>
                          )}
                        </section>

                        <section className="investigation-result-group">
                          <div className="result-group-heading">
                            <div className="result-group-icon unknowns-icon">
                              <AlertCircle size={17} />
                            </div>
                            <div>
                              <h3>Unknowns and evidence gaps</h3>
                              <p>
                                Information that remains unverified
                              </p>
                            </div>
                          </div>

                          {investigationResult.unknowns.length ===
                          0 ? (
                            <p className="empty-state">
                              No additional unknowns reported.
                            </p>
                          ) : (
                            <ul className="unknown-list">
                              {investigationResult.unknowns.map(
                                (unknown, index) => (
                                  <li key={`${unknown}-${index}`}>
                                    {unknown}
                                  </li>
                                ),
                              )}
                            </ul>
                          )}
                        </section>
                      </div>
                    )}
                  </section>
                </div>

                <aside className="detail-side-column">
                  <section className="content-panel side-panel">
                    <div className="side-panel-heading">
                      <h3>Incident status</h3>
                      <Activity size={17} />
                    </div>

                    <StatusBadge
                      status={selectedIncident.status}
                    />

                    <label className="side-status-label">
                      Update status
                      <select
                        value={selectedIncident.status}
                        disabled={updatingIncidentIds.includes(
                          selectedIncident.id,
                        )}
                        onChange={(event) =>
                          handleStatusChange(
                            selectedIncident.id,
                            event.target
                              .value as Incident['status'],
                          )
                        }
                      >
                        <option value="open">Open</option>
                        <option value="investigating">
                          Investigating
                        </option>
                        <option value="resolved">
                          Resolved
                        </option>
                      </select>
                    </label>

                    {updatingIncidentIds.includes(
                      selectedIncident.id,
                    ) && (
                      <p className="status-saving">
                        Saving status...
                      </p>
                    )}

                    {statusUpdateErrors[selectedIncident.id] && (
                      <p
                        className="error-message"
                        role="alert"
                      >
                        {statusUpdateErrors[selectedIncident.id]}
                      </p>
                    )}
                  </section>

                  <section className="content-panel side-panel">
                    <div className="side-panel-heading">
                      <h3>Incident metadata</h3>
                      <Layers3 size={17} />
                    </div>

                    <div className="side-metadata-list">
                      <div>
                        <span>Reference</span>
                        <strong>
                          {getIncidentReference(selectedIncident.id)}
                        </strong>
                      </div>
                      <div>
                        <span>Severity</span>
                        <SeverityBadge
                          severity={selectedIncident.severity}
                        />
                      </div>
                      <div>
                        <span>Service</span>
                        <strong>
                          {selectedIncident.service}
                        </strong>
                      </div>
                      <div>
                        <span>Environment</span>
                        <strong>
                          {selectedIncident.environment ?? 'Unknown'}
                        </strong>
                      </div>
                      <div>
                        <span>Evidence records</span>
                        <strong>{evidence.length}</strong>
                      </div>
                    </div>
                  </section>

                  <section className="ai-assistant-card">
                    <div className="ai-assistant-icon">
                      <Sparkles size={20} />
                    </div>
                    <h3>AI-powered investigation</h3>
                    <p>
                      OpsPilot analyzes available evidence to
                      distinguish confirmed facts from possible
                      causes.
                    </p>
                    <div className="ai-assistant-footer">
                      <span>
                        <ShieldAlert size={14} />
                        Evidence-grounded
                      </span>
                    </div>
                  </section>
                </aside>
              </div>
            </div>
          ) : activePage === 'overview' ? (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    OPERATIONS CENTER
                  </div>
                  <h1>Overview</h1>
                  <p className="page-description">
                    Monitor your incidents, prioritize issues,
                    and investigate operational problems.
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
                  <Plus size={17} />
                  New incident
                </button>
              </div>

              <div className="overview-welcome">
                <div className="welcome-content">
                  <div className="welcome-label">
                    <Sparkles size={14} />
                    YOUR OPERATIONS WORKSPACE
                  </div>
                  <h2>
                    Stay ahead of incidents.
                    <br />
                    <span>Investigate with confidence.</span>
                  </h2>
                  <p>
                    Bring incident reports, operational evidence,
                    and AI-assisted investigation together in one
                    workspace.
                  </p>
                  <button
                    className="welcome-button"
                    type="button"
                    onClick={() => setActivePage('incidents')}
                  >
                    Explore incidents
                    <ArrowRight size={16} />
                  </button>
                </div>

                <div className="welcome-visual" aria-hidden="true">
                  <div className="visual-orbit orbit-one" />
                  <div className="visual-orbit orbit-two" />
                  <div className="visual-core">
                    <Activity size={38} />
                  </div>
                  <div className="visual-node node-one">
                    <Server size={17} />
                  </div>
                  <div className="visual-node node-two">
                    <Bot size={17} />
                  </div>
                  <div className="visual-node node-three">
                    <Zap size={17} />
                  </div>
                </div>
              </div>

              <div className="section-heading overview-section-heading">
                <div>
                  <h2>Incident metrics</h2>
                  <p>
                    A snapshot of your operational workload
                  </p>
                </div>
                <span className="live-label">
                  <span className="system-online-dot" />
                  Live data
                </span>
              </div>

              <div className="metrics-grid">
                <article className="metric-card">
                  <div className="metric-card-top">
                    <span className="metric-icon metric-icon-blue">
                      <Layers3 size={19} />
                    </span>
                    <span className="metric-label">
                      Total incidents
                    </span>
                  </div>
                  <div className="metric-value">
                    {isLoadingIncidents
                      ? '—'
                      : incidents.length}
                  </div>
                  <div className="metric-description">
                    <span>All registered incidents</span>
                    <ArrowUpRight size={15} />
                  </div>
                </article>

                <article className="metric-card">
                  <div className="metric-card-top">
                    <span className="metric-icon metric-icon-orange">
                      <Activity size={19} />
                    </span>
                    <span className="metric-label">
                      Active incidents
                    </span>
                  </div>
                  <div className="metric-value">
                    {isLoadingIncidents
                      ? '—'
                      : activeIncidentCount}
                  </div>
                  <div className="metric-description">
                    <span>Not yet resolved</span>
                    <span className="metric-dot orange-dot" />
                  </div>
                </article>

                <article className="metric-card">
                  <div className="metric-card-top">
                    <span className="metric-icon metric-icon-red">
                      <AlertTriangle size={19} />
                    </span>
                    <span className="metric-label">
                      Critical incidents
                    </span>
                  </div>
                  <div className="metric-value">
                    {isLoadingIncidents
                      ? '—'
                      : criticalIncidentCount}
                  </div>
                  <div className="metric-description">
                    <span>Unresolved critical issues</span>
                    <span className="metric-dot red-dot" />
                  </div>
                </article>

                <article className="metric-card">
                  <div className="metric-card-top">
                    <span className="metric-icon metric-icon-green">
                      <CheckCircle2 size={19} />
                    </span>
                    <span className="metric-label">
                      Resolved incidents
                    </span>
                  </div>
                  <div className="metric-value">
                    {isLoadingIncidents
                      ? '—'
                      : resolvedIncidentCount}
                  </div>
                  <div className="metric-description">
                    <span>Successfully resolved</span>
                    <span className="metric-dot green-dot" />
                  </div>
                </article>
              </div>

              {loadError && (
                <div className="error-banner" role="alert">
                  <AlertCircle size={17} />
                  <span>{loadError}</span>
                  <button
                    type="button"
                    onClick={() => window.location.reload()}
                    aria-label="Reload page"
                  >
                    <RefreshCw size={15} />
                    Retry
                  </button>
                </div>
              )}

              <div className="overview-lower-grid">
                <section className="content-panel recent-incidents-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Recent incidents</h2>
                      <p>
                        Your latest reported operational issues
                      </p>
                    </div>

                    <button
                      className="text-button"
                      type="button"
                      onClick={() => setActivePage('incidents')}
                    >
                      View all
                      <ArrowRight size={15} />
                    </button>
                  </div>

                  {isLoadingIncidents ? (
                    <div className="loading-state">
                      <LoaderCircle
                        size={19}
                        className="spin-icon"
                      />
                      Loading incidents...
                    </div>
                  ) : incidents.length === 0 ? (
                    <EmptyState
                      icon={Layers3}
                      title="No incidents yet"
                      description="Create your first incident to start using your operations workspace."
                    />
                  ) : (
                    <div className="recent-incident-list">
                      {recentIncidents.map((incident) => (
                        <button
                          className="recent-incident-row"
                          type="button"
                          key={incident.id}
                          onClick={() =>
                            openIncident(incident.id)
                          }
                        >
                          <div className="recent-incident-icon">
                            <AlertCircle size={17} />
                          </div>

                          <div className="recent-incident-info">
                            <strong>{incident.title}</strong>
                            <span>
                              {getIncidentReference(incident.id)}
                              {' · '}
                              {incident.service}
                            </span>
                          </div>

                          <div className="recent-incident-meta">
                            <SeverityBadge
                              severity={incident.severity}
                            />
                            <span>
                              {formatRelativeDate(incident.created_at)}
                            </span>
                          </div>

                          <ChevronRight
                            size={16}
                            className="recent-row-arrow"
                          />
                        </button>
                      ))}
                    </div>
                  )}
                </section>

                <section className="content-panel priority-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Priority overview</h2>
                      <p>
                        Current unresolved workload
                      </p>
                    </div>
                    <ShieldAlert size={19} />
                  </div>

                  <div className="priority-highlight">
                    <span className="priority-highlight-label">
                      High-priority incidents
                    </span>
                    <strong>
                      {isLoadingIncidents
                        ? '—'
                        : highPriorityCount}
                    </strong>
                    <span>
                      Critical and high severity
                    </span>
                  </div>

                  <div className="priority-breakdown">
                    <div className="priority-row">
                      <span className="priority-dot priority-critical" />
                      <span>Critical</span>
                      <strong>
                        {isLoadingIncidents
                          ? '—'
                          : incidents.filter(
                              (incident) =>
                                incident.severity === 'critical' &&
                                incident.status !== 'resolved',
                            ).length}
                      </strong>
                    </div>
                    <div className="priority-row">
                      <span className="priority-dot priority-high" />
                      <span>High</span>
                      <strong>
                        {isLoadingIncidents
                          ? '—'
                          : incidents.filter(
                              (incident) =>
                                incident.severity === 'high' &&
                                incident.status !== 'resolved',
                            ).length}
                      </strong>
                    </div>
                    <div className="priority-row">
                      <span className="priority-dot priority-medium" />
                      <span>Medium</span>
                      <strong>
                        {isLoadingIncidents
                          ? '—'
                          : incidents.filter(
                              (incident) =>
                                incident.severity === 'medium' &&
                                incident.status !== 'resolved',
                            ).length}
                      </strong>
                    </div>
                    <div className="priority-row">
                      <span className="priority-dot priority-low" />
                      <span>Low</span>
                      <strong>
                        {isLoadingIncidents
                          ? '—'
                          : incidents.filter(
                              (incident) =>
                                incident.severity === 'low' &&
                                incident.status !== 'resolved',
                            ).length}
                      </strong>
                    </div>
                  </div>

                  <button
                    className="priority-link"
                    type="button"
                    onClick={() => {
                      setSeverityFilter('critical')
                      setActivePage('incidents')
                    }}
                  >
                    Review critical incidents
                    <ArrowRight size={15} />
                  </button>
                </section>
              </div>

              <div className="overview-footer-note">
                <div>
                  <span className="system-online-dot" />
                  OpsPilot workspace
                </div>
                <span>
                  Incident intelligence · Evidence-based analysis
                </span>
              </div>
            </>
          ) : activePage === 'investigator' ? (
            <div className="tool-workspace">
              <div className="page-heading">
                <div>
                  <div className="eyebrow">AI-POWERED OPERATIONS</div>
                  <h1>AI Investigator</h1>
                  <p className="page-description">
                    Run evidence-grounded investigations, review saved findings,
                    and distinguish confirmed facts from possible causes.
                  </p>
                </div>
                <button
                  className="primary-button"
                  type="button"
                  onClick={handleInvestigation}
                  disabled={
                    !selectedIncidentId ||
                    isInvestigating ||
                    isLoadingEvidence ||
                    isLoadingInvestigationHistory
                  }
                >
                  {isInvestigating ? (
                    <LoaderCircle size={16} className="spin-icon" />
                  ) : (
                    <Sparkles size={16} />
                  )}
                  {isInvestigating ? 'Investigating...' : 'Run investigation'}
                </button>
              </div>

              <section className="content-panel tool-context-panel">
                <div className="tool-context-copy">
                  <div className="panel-title-row">
                    <Bot size={19} />
                    <h2>Investigation target</h2>
                  </div>
                  <p>Select an incident to load its evidence and investigation history.</p>
                </div>
                <label className="tool-incident-select">
                  <span>Incident</span>
                  <select
                    value={selectedIncidentId ?? ''}
                    onChange={(event) =>
                      setSelectedIncidentId(
                        event.target.value ? Number(event.target.value) : null,
                      )
                    }
                    aria-label="Select incident for AI investigation"
                    disabled={isLoadingIncidents || incidents.length === 0}
                  >
                    <option value="">Select an incident</option>
                    {incidents.map((incident) => (
                      <option key={incident.id} value={incident.id}>
                        {getIncidentReference(incident.id)} · {incident.title}
                      </option>
                    ))}
                  </select>
                </label>
              </section>

              {isLoadingIncidents ? (
                <div className="content-panel">
                  <div className="loading-state">
                    <LoaderCircle size={19} className="spin-icon" />
                    Loading incidents...
                  </div>
                </div>
              ) : incidents.length === 0 ? (
                <div className="content-panel">
                  <EmptyState
                    icon={Bot}
                    title="No incident to investigate"
                    description="Create an incident first. You can then attach evidence and run an AI investigation."
                  />
                  <div className="tool-empty-action">
                    <button
                      className="primary-button"
                      type="button"
                      onClick={() => {
                        setError('')
                        setIsFormOpen(true)
                      }}
                    >
                      <Plus size={16} />
                      Create incident
                    </button>
                  </div>
                </div>
              ) : !selectedIncident ? (
                <div className="content-panel">
                  <EmptyState
                    icon={Search}
                    title="Choose an incident"
                    description="Select an incident above to inspect its saved investigation or run a new evidence-based analysis."
                  />
                </div>
              ) : (
                <>
                  <section className="tool-incident-summary content-panel">
                    <div>
                      <div className="eyebrow">
                        {getIncidentReference(selectedIncident.id)} · INVESTIGATION TARGET
                      </div>
                      <h2>{selectedIncident.title}</h2>
                      <p>{selectedIncident.description}</p>
                    </div>
                    <div className="tool-summary-badges">
                      <SeverityBadge severity={selectedIncident.severity} />
                      <StatusBadge status={selectedIncident.status} />
                    </div>
                    <div className="tool-summary-meta">
                      <span><Server size={14} /> {selectedIncident.service}</span>
                      <span><Layers3 size={14} /> {selectedIncident.environment ?? 'Unknown'}</span>
                      <span><FileText size={14} /> {evidence.length} evidence records</span>
                    </div>
                  </section>

                  <section className="content-panel investigation-panel tool-investigation-panel">
                    <div className="panel-heading">
                      <div>
                        <div className="panel-title-row">
                          <Sparkles size={19} />
                          <h2>Investigation results</h2>
                          {investigationHistory.length > 0 && (
                            <span className="count-badge">{investigationHistory.length}</span>
                          )}
                        </div>
                        <p>AI findings are grounded in the selected incident's evidence.</p>
                      </div>
                      <button
                        className="secondary-button"
                        type="button"
                        onClick={() => navigateTo('evidence')}
                      >
                        <FileText size={15} />
                        Review evidence
                      </button>
                    </div>

                    {evidenceLoadError && (
                      <p className="error-message" role="alert">{evidenceLoadError}</p>
                    )}
                    {investigationError && (
                      <p className="error-message" role="alert">{investigationError}</p>
                    )}
                    {isLoadingEvidence && (
                      <div className="loading-state">
                        <LoaderCircle size={18} className="spin-icon" />
                        Loading incident evidence...
                      </div>
                    )}
                    {isLoadingInvestigationHistory && (
                      <div className="loading-state">
                        <LoaderCircle size={18} className="spin-icon" />
                        Loading saved investigations...
                      </div>
                    )}
                    {isInvestigating && (
                      <div className="investigation-progress">
                        <div className="investigation-progress-icon"><Sparkles size={19} /></div>
                        <div>
                          <strong>Investigation in progress</strong>
                          <p>Reviewing the available evidence and generating structured findings.</p>
                        </div>
                      </div>
                    )}

                    {!isLoadingInvestigationHistory && investigationHistory.length > 0 && (
                      <div className="history-summary">
                        <Clock3 size={15} />
                        <span>{investigationHistory.length} saved investigation{investigationHistory.length === 1 ? '' : 's'}</span>
                        <span className="history-separator">·</span>
                        <span>Latest: {formatDate(investigationHistory[0].created_at)}</span>
                      </div>
                    )}

                    {!isLoadingInvestigationHistory && !isInvestigating && !investigationError && !investigationResult && (
                      <EmptyState
                        icon={Bot}
                        title="Ready to investigate"
                        description="Run an investigation to identify observed facts, possible causes, recommended checks, and evidence gaps."
                      />
                    )}

                    {investigationResult && (
                      <div className="investigation-results">
                        <div className="investigation-result-banner">
                          <div className="result-banner-icon"><CheckCircle2 size={18} /></div>
                          <div>
                            <strong>Investigation completed</strong>
                            <p>Review each finding and its supporting evidence before acting on a hypothesis.</p>
                          </div>
                        </div>

                        <section className="investigation-result-group">
                          <div className="result-group-heading">
                            <div className="result-group-icon facts-icon"><CheckCircle2 size={17} /></div>
                            <div><h3>Observed facts</h3><p>Findings supported by evidence</p></div>
                            <span className="count-badge">{investigationResult.observed_facts.length}</span>
                          </div>
                          {investigationResult.observed_facts.length === 0 ? (
                            <p className="empty-state">No confirmed facts identified.</p>
                          ) : (
                            <div className="investigation-list">
                              {investigationResult.observed_facts.map((fact, index) => (
                                <article className="investigation-result-card" key={`${fact.statement}-${index}`}>
                                  <p>{fact.statement}</p>
                                  <div className="evidence-reference">
                                    <FileText size={13} />
                                    Evidence IDs: {fact.evidence_ids.join(', ')}
                                  </div>
                                </article>
                              ))}
                            </div>
                          )}
                        </section>

                        <section className="investigation-result-group">
                          <div className="result-group-heading">
                            <div className="result-group-icon hypotheses-icon"><LightbulbIcon /></div>
                            <div><h3>Possible causes</h3><p>Hypotheses requiring validation</p></div>
                            <span className="count-badge">{investigationResult.hypotheses.length}</span>
                          </div>
                          {investigationResult.hypotheses.length === 0 ? (
                            <p className="empty-state">No hypotheses generated.</p>
                          ) : (
                            <div className="investigation-list">
                              {investigationResult.hypotheses.map((hypothesis, index) => (
                                <article className="investigation-result-card" key={`${hypothesis.explanation}-${index}`}>
                                  <p>{hypothesis.explanation}</p>
                                  <span className={`confidence-badge confidence-${hypothesis.confidence}`}>
                                    {hypothesis.confidence.toUpperCase()} confidence
                                  </span>
                                  <div className="evidence-reference">
                                    <FileText size={13} />
                                    Supporting evidence: {hypothesis.supporting_evidence_ids.length > 0 ? hypothesis.supporting_evidence_ids.join(', ') : 'None'}
                                  </div>
                                </article>
                              ))}
                            </div>
                          )}
                        </section>

                        <section className="investigation-result-group">
                          <div className="result-group-heading">
                            <div className="result-group-icon checks-icon"><ShieldAlert size={17} /></div>
                            <div><h3>Recommended checks</h3><p>Suggested next investigation steps</p></div>
                          </div>
                          {investigationResult.recommended_checks.length === 0 ? (
                            <p className="empty-state">No additional checks recommended.</p>
                          ) : (
                            <ul className="recommendation-list">
                              {investigationResult.recommended_checks.map((check, index) => (
                                <li key={`${check}-${index}`}>
                                  <span className="recommendation-number">{index + 1}</span>
                                  {check}
                                </li>
                              ))}
                            </ul>
                          )}
                        </section>

                        <section className="investigation-result-group">
                          <div className="result-group-heading">
                            <div className="result-group-icon unknowns-icon"><AlertCircle size={17} /></div>
                            <div><h3>Unknowns and evidence gaps</h3><p>Information that remains unverified</p></div>
                          </div>
                          {investigationResult.unknowns.length === 0 ? (
                            <p className="empty-state">No additional unknowns reported.</p>
                          ) : (
                            <ul className="unknown-list">
                              {investigationResult.unknowns.map((unknown, index) => (
                                <li key={`${unknown}-${index}`}>{unknown}</li>
                              ))}
                            </ul>
                          )}
                        </section>
                      </div>
                    )}
                  </section>

                  {investigationResult && (
                    <EvidenceRelationshipGraph
                      result={investigationResult}
                      evidence={evidence}
                    />
                  )}

                  <section className="content-panel activity-timeline-panel">
                    <div className="panel-heading">
                      <div>
                        <div className="panel-title-row">
                          <CalendarClock size={18} />
                          <h2>Investigation timeline</h2>
                        </div>
                        <p>Chronological record of available incident evidence and investigation runs.</p>
                      </div>
                      <span className="count-badge">{evidence.length + investigationHistory.length + 1}</span>
                    </div>
                    {isLoadingEvidence || isLoadingInvestigationHistory ? (
                      <div className="loading-state"><LoaderCircle size={17} className="spin-icon" /> Building incident timeline...</div>
                    ) : (
                      <div className="activity-timeline">
                        <article className="timeline-event timeline-incident">
                          <span className="timeline-marker"><AlertTriangle size={13} /></span>
                          <div className="timeline-event-content">
                            <strong>Incident reported</strong>
                            <p>{selectedIncident.title}</p>
                            <time>{formatDate(selectedIncident.created_at)}</time>
                          </div>
                        </article>
                        {[
                          ...evidence.map((item) => ({
                            key: `evidence-${item.id}`,
                            kind: 'evidence' as const,
                            date: item.created_at,
                            title: `${item.source_type} evidence added`,
                            description: `Evidence #${item.id} · ${item.content.slice(0, 180)}`,
                          })),
                          ...investigationHistory.map((record, index) => ({
                            key: `investigation-${index}-${record.created_at}`,
                            kind: 'investigation' as const,
                            date: record.created_at,
                            title: 'AI investigation completed',
                            description: `${record.result.observed_facts.length} observed facts · ${record.result.hypotheses.length} hypotheses`,
                          })),
                        ]
                          .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
                          .map((event) => (
                            <article className={`timeline-event timeline-${event.kind}`} key={event.key}>
                              <span className="timeline-marker">{event.kind === 'evidence' ? <FileText size={13} /> : <Sparkles size={13} />}</span>
                              <div className="timeline-event-content">
                                <strong>{event.title}</strong>
                                <p>{event.description}</p>
                                <time>{formatDate(event.date)}</time>
                              </div>
                            </article>
                          ))}
                      </div>
                    )}
                  </section>
                </>
              )}
            </div>
          ) : activePage === 'evidence' ? (
            <div className="tool-workspace">
              <div className="page-heading">
                <div>
                  <div className="eyebrow">INCIDENT DATA</div>
                  <h1>Evidence</h1>
                  <p className="page-description">
                    Collect and review the logs, metrics, traces, deployments,
                    and notes used during incident investigation.
                  </p>
                </div>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => navigateTo('investigator')}
                  disabled={!selectedIncidentId}
                >
                  <Bot size={16} />
                  Open AI Investigator
                </button>
              </div>

              <section className="content-panel tool-context-panel">
                <div className="tool-context-copy">
                  <div className="panel-title-row">
                    <FileText size={19} />
                    <h2>Evidence source</h2>
                  </div>
                  <p>Choose which incident this evidence belongs to.</p>
                </div>
                <label className="tool-incident-select">
                  <span>Incident</span>
                  <select
                    value={selectedIncidentId ?? ''}
                    onChange={(event) =>
                      setSelectedIncidentId(
                        event.target.value ? Number(event.target.value) : null,
                      )
                    }
                    aria-label="Select incident for evidence"
                    disabled={isLoadingIncidents || incidents.length === 0}
                  >
                    <option value="">Select an incident</option>
                    {incidents.map((incident) => (
                      <option key={incident.id} value={incident.id}>
                        {getIncidentReference(incident.id)} · {incident.title}
                      </option>
                    ))}
                  </select>
                </label>
              </section>

              {isLoadingIncidents ? (
                <div className="content-panel">
                  <div className="loading-state">
                    <LoaderCircle size={19} className="spin-icon" />
                    Loading incidents...
                  </div>
                </div>
              ) : incidents.length === 0 ? (
                <div className="content-panel">
                  <EmptyState
                    icon={FileText}
                    title="No incident available"
                    description="Create an incident before attaching operational evidence."
                  />
                  <div className="tool-empty-action">
                    <button
                      className="primary-button"
                      type="button"
                      onClick={() => {
                        setError('')
                        setIsFormOpen(true)
                      }}
                    >
                      <Plus size={16} />
                      Create incident
                    </button>
                  </div>
                </div>
              ) : !selectedIncident ? (
                <div className="content-panel">
                  <EmptyState
                    icon={FileText}
                    title="Select an incident"
                    description="Choose an incident above to view its evidence records or add new supporting data."
                  />
                </div>
              ) : (
                <>
                  <section className="tool-incident-summary content-panel">
                    <div>
                      <div className="eyebrow">
                        {getIncidentReference(selectedIncident.id)} · SELECTED INCIDENT
                      </div>
                      <h2>{selectedIncident.title}</h2>
                      <p>{selectedIncident.description}</p>
                    </div>
                    <div className="tool-summary-badges">
                      <SeverityBadge severity={selectedIncident.severity} />
                      <StatusBadge status={selectedIncident.status} />
                    </div>
                    <div className="tool-summary-meta">
                      <span><Server size={14} /> {selectedIncident.service}</span>
                      <span><Layers3 size={14} /> {selectedIncident.environment ?? 'Unknown'}</span>
                      <span><FileText size={14} /> {evidence.length} evidence records</span>
                    </div>
                  </section>

                  <div className="tool-evidence-grid">
                    <section className="content-panel">
                      <div className="panel-heading">
                        <div>
                          <div className="panel-title-row">
                            <FileText size={18} />
                            <h2>Evidence records</h2>
                            <span className="count-badge">{evidence.length}</span>
                          </div>
                          <p>Search and filter the supporting records attached to this incident.</p>
                        </div>
                      </div>

                      <div className="evidence-toolbar">
                        <label className="evidence-search-field">
                          <Search size={15} />
                          <input
                            type="search"
                            value={evidenceSearch}
                            onChange={(event) => setEvidenceSearch(event.target.value)}
                            placeholder="Search evidence content or ID..."
                            aria-label="Search evidence"
                          />
                          {evidenceSearch && (
                            <button type="button" aria-label="Clear evidence search" onClick={() => setEvidenceSearch('')}><X size={14} /></button>
                          )}
                        </label>
                        <label className="evidence-type-filter">
                          <SlidersHorizontal size={14} />
                          <select
                            value={evidenceTypeFilter}
                            onChange={(event) => setEvidenceTypeFilter(event.target.value as EvidenceSourceType | 'all')}
                            aria-label="Filter evidence by type"
                          >
                            <option value="all">All types</option>
                            <option value="log">Logs</option>
                            <option value="metric">Metrics</option>
                            <option value="trace">Traces</option>
                            <option value="deployment">Deployments</option>
                            <option value="note">Notes</option>
                          </select>
                        </label>
                      </div>

                      {isLoadingEvidence ? (
                        <div className="loading-state">
                          <LoaderCircle size={18} className="spin-icon" />
                          Loading evidence...
                        </div>
                      ) : evidenceLoadError ? (
                        <p className="error-message" role="alert">{evidenceLoadError}</p>
                      ) : evidence.length === 0 ? (
                        <EmptyState
                          icon={FileText}
                          title="No evidence added"
                          description="Add the first log, metric, trace, deployment record, or note using the form."
                        />
                      ) : filteredEvidence.length === 0 ? (
                        <EmptyState
                          icon={Search}
                          title="No matching evidence"
                          description="Try another search term or clear the evidence type filter."
                        />
                      ) : (
                        <div className="evidence-list">
                          <div className="evidence-result-count">Showing {filteredEvidence.length} of {evidence.length} records</div>
                          {filteredEvidence.map((item) => (
                            <article className="evidence-card" id={`evidence-record-${item.id}`} key={item.id}>
                              <div className="evidence-card-header">
                                <div className="evidence-type">
                                  <Terminal size={15} />
                                  <span>{item.source_type}</span>
                                </div>
                                <span className="evidence-date">{formatRelativeDate(item.created_at)}</span>
                              </div>
                              <pre className="evidence-content">{item.content}</pre>
                              <div className="evidence-card-footer">
                                <span>Evidence #{item.id}</span>
                                <span>{formatDate(item.created_at)}</span>
                              </div>
                            </article>
                          ))}
                        </div>
                      )}
                    </section>

                    <section className="content-panel tool-add-evidence-panel">
                      <div className="panel-heading">
                        <div>
                          <div className="panel-title-row">
                            <Plus size={18} />
                            <h2>Add evidence</h2>
                          </div>
                          <p>Attach a new source to the selected incident.</p>
                        </div>
                      </div>
                      <form className="evidence-form" onSubmit={handleEvidenceSubmit}>
                        <div className="form-group">
                          <label htmlFor="workspace-evidence-source-type">Evidence type</label>
                          <select
                            id="workspace-evidence-source-type"
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
                          <label htmlFor="workspace-evidence-content">Evidence content</label>
                          <textarea
                            id="workspace-evidence-content"
                            value={evidenceForm.content}
                            onChange={(event) =>
                              setEvidenceForm((current) => ({
                                ...current,
                                content: event.target.value,
                              }))
                            }
                            placeholder="Paste logs, metrics, traces, deployment details, or investigation notes..."
                            rows={9}
                            maxLength={20000}
                            required
                          />
                          <span className="character-count">
                            {evidenceForm.content.length.toLocaleString()} / 20,000 characters
                          </span>
                        </div>
                        {evidenceSubmitError && (
                          <p className="error-message" role="alert">{evidenceSubmitError}</p>
                        )}
                        <div className="form-actions">
                          <button
                            className="primary-button"
                            type="submit"
                            disabled={
                              isSubmittingEvidence ||
                              !evidenceForm.content.trim() ||
                              isLoadingEvidence
                            }
                          >
                            {isSubmittingEvidence ? (
                              <LoaderCircle size={16} className="spin-icon" />
                            ) : (
                              <Plus size={16} />
                            )}
                            {isSubmittingEvidence ? 'Adding evidence...' : 'Add evidence'}
                          </button>
                        </div>
                      </form>
                    </section>
                  </div>
                </>
              )}
            </div>
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    OPERATIONS CENTER
                  </div>
                  <h1>Incidents</h1>
                  <p className="page-description">
                    Search, prioritize, and manage reported
                    operational incidents.
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
                  <Plus size={17} />
                  New incident
                </button>
              </div>

              <div className="incident-summary-strip">
                <div>
                  <span className="summary-strip-label">
                    Total incidents
                  </span>
                  <strong>
                    {isLoadingIncidents ? '—' : incidents.length}
                  </strong>
                </div>
                <div>
                  <span className="summary-strip-label">
                    Active
                  </span>
                  <strong>
                    {isLoadingIncidents ? '—' : activeIncidentCount}
                  </strong>
                </div>
                <div>
                  <span className="summary-strip-label">
                    Critical
                  </span>
                  <strong className="summary-critical">
                    {isLoadingIncidents ? '—' : criticalIncidentCount}
                  </strong>
                </div>
                <div>
                  <span className="summary-strip-label">
                    Resolved
                  </span>
                  <strong className="summary-resolved">
                    {isLoadingIncidents ? '—' : resolvedIncidentCount}
                  </strong>
                </div>
              </div>

              {loadError && (
                <div className="error-banner" role="alert">
                  <AlertCircle size={17} />
                  {loadError}
                </div>
              )}

              {isLoadingIncidents ? (
                <div className="content-panel">
                  <div className="loading-state">
                    <LoaderCircle
                      size={20}
                      className="spin-icon"
                    />
                    Loading incidents...
                  </div>
                </div>
              ) : incidents.length === 0 ? (
                <div className="content-panel">
                  <EmptyState
                    icon={Layers3}
                    title="No incidents yet"
                    description="Create your first incident to start tracking operational issues."
                  />
                </div>
              ) : (
                <section className="content-panel incidents-table-panel">
                  <div className="panel-heading incidents-list-heading">
                    <div>
                      <h2>All incidents</h2>
                      <p>
                        Showing {displayedIncidents.length} of{' '}
                        {incidents.length} incidents
                      </p>
                    </div>

                    <span className="list-live-label">
                      <span className="system-online-dot" />
                      Workspace data
                    </span>
                  </div>

                  <div className="incident-toolbar">
                    <div className="incident-search">
                      <Search size={17} />
                      <input
                        type="search"
                        placeholder="Search incidents, services, or IDs..."
                        value={searchQuery}
                        onChange={(event) =>
                          setSearchQuery(event.target.value)
                        }
                        aria-label="Search incidents"
                      />
                      {searchQuery && (
                        <button
                          type="button"
                          onClick={() => setSearchQuery('')}
                          aria-label="Clear search"
                        >
                          <X size={15} />
                        </button>
                      )}
                    </div>

                    <div className="incident-filter-controls">
                      <label className="filter-control">
                        <Filter size={15} />
                        <select
                          value={statusFilter}
                          onChange={(event) =>
                            setStatusFilter(
                              event.target.value as IncidentStatusFilter,
                            )
                          }
                          aria-label="Filter by status"
                        >
                          <option value="all">All statuses</option>
                          <option value="open">Open</option>
                          <option value="investigating">
                            Investigating
                          </option>
                          <option value="resolved">Resolved</option>
                        </select>
                      </label>

                      <label className="filter-control">
                        <AlertTriangle size={15} />
                        <select
                          value={severityFilter}
                          onChange={(event) =>
                            setSeverityFilter(
                              event.target.value as IncidentSeverityFilter,
                            )
                          }
                          aria-label="Filter by severity"
                        >
                          <option value="all">All severities</option>
                          <option value="critical">Critical</option>
                          <option value="high">High</option>
                          <option value="medium">Medium</option>
                          <option value="low">Low</option>
                        </select>
                      </label>

                      <label className="filter-control">
                        <Server size={15} />
                        <select
                          value={environmentFilter}
                          onChange={(event) =>
                            setEnvironmentFilter(
                              event.target
                                .value as IncidentEnvironmentFilter,
                            )
                          }
                          aria-label="Filter by environment"
                        >
                          <option value="all">All environments</option>
                          <option value="production">
                            Production
                          </option>
                          <option value="staging">Staging</option>
                          <option value="development">
                            Development
                          </option>
                        </select>
                      </label>

                      <label className="filter-control sort-control">
                        <select
                          value={sortOption}
                          onChange={(event) =>
                            setSortOption(
                              event.target.value as IncidentSortOption,
                            )
                          }
                          aria-label="Sort incidents"
                        >
                          <option value="newest">Newest first</option>
                          <option value="oldest">Oldest first</option>
                          <option value="severity-high">
                            Highest severity
                          </option>
                          <option value="severity-low">
                            Lowest severity
                          </option>
                        </select>
                      </label>
                    </div>
                  </div>

                  {(searchQuery ||
                    statusFilter !== 'all' ||
                    severityFilter !== 'all' ||
                    environmentFilter !== 'all') && (
                    <div className="active-filter-row">
                      <span>
                        <Filter size={14} />
                        Filters applied
                      </span>
                      <button
                        type="button"
                        onClick={resetFilters}
                      >
                        Clear all
                        <X size={13} />
                      </button>
                    </div>
                  )}

                  <div className="incidents-table-wrapper">
                    <table className="incidents-table">
                      <thead>
                        <tr>
                          <th>Incident</th>
                          <th>Severity</th>
                          <th>Service</th>
                          <th>Environment</th>
                          <th>Status</th>
                          <th>Reported</th>
                          <th aria-label="Actions" />
                        </tr>
                      </thead>

                      <tbody>
                        {displayedIncidents.map((incident) => {
                          const isUpdating =
                            updatingIncidentIds.includes(incident.id)

                          return (
                            <tr key={incident.id}>
                              <td>
                                <button
                                  className="table-incident-link"
                                  type="button"
                                  onClick={() =>
                                    openIncident(incident.id)
                                  }
                                >
                                  <strong>{incident.title}</strong>
                                  <span>
                                    {getIncidentReference(incident.id)}
                                  </span>
                                </button>
                              </td>

                              <td>
                                <SeverityBadge
                                  severity={incident.severity}
                                />
                              </td>

                              <td>
                                <span className="table-service">
                                  <Server size={14} />
                                  {incident.service}
                                </span>
                              </td>

                              <td>
                                <span className="environment-label">
                                  {incident.environment ?? 'Unknown'}
                                </span>
                              </td>

                              <td>
                                <div className="table-status-cell">
                                  <select
                                    className={`table-status-select status-select-${incident.status}`}
                                    value={incident.status}
                                    disabled={isUpdating}
                                    onChange={(event) =>
                                      handleStatusChange(
                                        incident.id,
                                        event.target
                                          .value as Incident['status'],
                                      )
                                    }
                                    aria-label={`Status for ${incident.title}`}
                                  >
                                    <option value="open">Open</option>
                                    <option value="investigating">
                                      Investigating
                                    </option>
                                    <option value="resolved">
                                      Resolved
                                    </option>
                                  </select>
                                  {isUpdating && (
                                    <LoaderCircle
                                      size={14}
                                      className="spin-icon"
                                    />
                                  )}
                                </div>
                                {statusUpdateErrors[incident.id] && (
                                  <p
                                    className="status-update-error"
                                    role="alert"
                                  >
                                    {statusUpdateErrors[incident.id]}
                                  </p>
                                )}
                              </td>

                              <td>
                                <span className="table-date">
                                  {formatRelativeDate(incident.created_at)}
                                </span>
                              </td>

                              <td>
                                <button
                                  className="table-open-button"
                                  type="button"
                                  onClick={() =>
                                    openIncident(incident.id)
                                  }
                                  aria-label={`View ${incident.title}`}
                                >
                                  <ArrowUpRight size={16} />
                                </button>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>

                  {displayedIncidents.length === 0 && (
                    <EmptyState
                      icon={Search}
                      title="No matching incidents"
                      description="Try adjusting your search or clearing some filters."
                    />
                  )}
                </section>
              )}
            </>
          )}
        </section>
      </main>

      {isFormOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              closeForm()
            }
          }}
        >
          <section
            className="incident-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="incident-form-title"
          >
            <div className="modal-heading">
              <div className="modal-heading-icon">
                <AlertCircle size={20} />
              </div>

              <div className="modal-heading-copy">
                <p className="eyebrow">
                  INCIDENT OPERATIONS
                </p>
                <h2 id="incident-form-title">
                  Create an incident
                </h2>
                <p>
                  Add the initial details so your team can
                  investigate and resolve the issue.
                </p>
              </div>

              <button
                className="modal-close-button"
                type="button"
                onClick={closeForm}
                disabled={isSubmitting}
                aria-label="Close form"
              >
                <X size={19} />
              </button>
            </div>

            <form
              className="incident-form"
              onSubmit={handleSubmit}
            >
              <label>
                Incident title
                <input
                  value={form.title}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      title: event.target.value,
                    }))
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
                  placeholder="Describe what is happening, when it started, and its impact..."
                />
              </label>

              <div className="form-row">
                <label>
                  Affected service
                  <input
                    value={form.service}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        service: event.target.value,
                      }))
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
                        environment: event.target
                          .value as IncidentForm['environment'],
                      }))
                    }
                    required
                  >
                    <option value="">
                      Select environment
                    </option>
                    <option value="production">
                      Production
                    </option>
                    <option value="staging">Staging</option>
                    <option value="development">
                      Development
                    </option>
                  </select>
                </label>

                <label>
                  Severity
                  <select
                    value={form.severity}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        severity: event.target
                          .value as Incident['severity'],
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

              {error && (
                <p className="form-error" role="alert">
                  <AlertCircle size={15} />
                  {error}
                </p>
              )}

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
                  {isSubmitting ? (
                    <LoaderCircle
                      size={16}
                      className="spin-icon"
                    />
                  ) : (
                    <Plus size={16} />
                  )}
                  {isSubmitting
                    ? 'Creating incident...'
                    : 'Create incident'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  )
}

function LightbulbIcon() {
  return <Sparkles size={17} />
}

export default App
