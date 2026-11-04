import './App.css'

const navigationItems = [
  { label: 'Overview', icon: '▦', active: true },
  { label: 'Incidents', icon: '◉', active: false },
  { label: 'Knowledge Base', icon: '▤', active: false },
]

function App() {
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
            <button className="primary-button" type="button" disabled>
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
                Your dashboard will bring incidents, evidence, and investigation
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
              <div className="card-placeholder">—</div>
              <p>Incident tracking will appear here</p>
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
        </section>
      </main>
    </div>
  )
}

export default App