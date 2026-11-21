# OpsPilot

**Evidence-Driven AI Incident Investigation Platform**

OpsPilot is an AI-powered incident investigation platform designed to help engineers understand, investigate, and troubleshoot software incidents.

It combines incident management, evidence collection, log-pattern analysis, semantic retrieval, OpenTelemetry trace ingestion, service topology awareness, and structured AI-assisted investigation into a unified workflow.

The goal is to make incident investigation more systematic, explainable, and evidence-driven.

## Key Features

- **Incident Management:** Create, track, retrieve, and update software incidents.
- **Evidence Collection:** Associate logs, metrics, traces, deployment events, and investigation notes with incidents.
- **Log Pattern Analysis:** Normalize recurring log patterns and identify potentially relevant signals.
- **Semantic Evidence Retrieval:** Retrieve relevant historical evidence using semantic and lexical relevance.
- **OpenTelemetry Trace Ingestion:** Process trace data and extract service-level relationships.
- **Service Topology Awareness:** Use service relationships and topology signals to improve evidence retrieval.
- **AI-Assisted Investigation:** Generate structured facts, hypotheses, confidence assessments, recommended checks, and unknowns.
- **Evidence Validation:** Validate AI-generated findings against the evidence available in the investigation context.
- **Investigation History:** Persist investigation results for later review.
- **Structured Investigation Reports:** Combine incident details, retrieved evidence, analysis, and AI findings.
- **API Reliability:** Request IDs, health checks, database readiness checks, and centralized error handling.
- **Interactive Dashboard:** React and TypeScript interface for incident management and investigation.

## Architecture

```mermaid
flowchart TD
    A[React + TypeScript Dashboard] --> B[FastAPI Backend]
    B --> C[Incident Management]
    B --> D[Evidence Ingestion]
    D --> E[Log Pattern Analysis]
    D --> F[OpenTelemetry Trace Processing]
    F --> G[Service Topology]
    E --> H[Evidence Retrieval]
    G --> H
    H --> I[Incident Context Builder]
    I --> J[AI Investigation Service]
    J --> K[Evidence Validation]
    K --> L[Structured Findings]
    B --> M[PostgreSQL]
    J --> N[Ollama / OpenAI]
    L --> M
    B --> O[Investigation Reports]
```

### Investigation Workflow

1. An engineer creates an incident through the dashboard.
2. Relevant evidence is attached to the incident.
3. OpsPilot processes evidence and identifies useful patterns.
4. The retrieval system searches for relevant evidence.
5. The investigation context is assembled with bounded evidence and source references.
6. The AI investigation service generates structured findings and hypotheses.
7. Evidence validation checks that referenced evidence exists in the investigation context.
8. The investigation result is saved and can be reviewed later.
9. A structured report can be generated using incident details and retrieved evidence.

## Technology Stack

| Layer | Technologies |
|---|---|
| Backend | Python, FastAPI |
| Database | PostgreSQL, SQLAlchemy |
| Database Migrations | Alembic |
| AI Integration | Ollama, OpenAI API |
| Language Models | Qwen models |
| Embeddings | all-minilm |
| Retrieval | Semantic and lexical retrieval |
| Observability | OpenTelemetry trace processing |
| Frontend | React, TypeScript, Vite |
| Testing | Pytest, ESLint, TypeScript |
| Version Control | Git, GitHub |

## Project Structure

```text
opspilot/
├── app/
│   ├── main.py
│   ├── models.py
│   ├── db_models.py
│   ├── database.py
│   ├── config.py
│   ├── analyzer.py
│   ├── chunking.py
│   ├── embeddings.py
│   ├── retrieval.py
│   ├── retrieval_service.py
│   ├── report_builder.py
│   ├── ai_models.py
│   ├── evidence_validation.py
│   ├── llm_client.py
│   ├── incident_context.py
│   └── investigation_service.py
├── experiments/
│   └── topology retrieval experiments and evaluation datasets
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── migrations/
├── scripts/
├── tests/
├── requirements.txt
├── requirements-db.txt
├── TESTING.md
└── README.md
```

## Prerequisites

- Python 3.13 (used during project development and testing)
- Node.js and npm
- PostgreSQL
- Ollama for local AI inference
- Git

## Local Setup

### 1. Clone the repository

```powershell
git clone https://github.com/ChahatTyagi/opspilot.git
cd opspilot
```

### 2. Set up the Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-db.txt
```

### 3. Configure PostgreSQL

Create a PostgreSQL database for OpsPilot.

For example:

```sql
CREATE DATABASE opspilot;
```

Configure the database connection through the `DATABASE_URL` environment variable.

### 4. Configure Ollama

Install Ollama and make sure its local service is running.

Pull the models used by the local configuration:

```powershell
ollama pull qwen3:4b
ollama pull qwen3.5:9b-q4_K_M
ollama pull all-minilm
```

Create a `.env` file in the repository root:

```env
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/opspilot

LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_TIMEOUT_SECONDS=300

VERIFIER_MODEL=qwen3.5:9b-q4_K_M

EMBEDDING_PROVIDER=ollama
OLLAMA_EMBEDDING_MODEL=all-minilm
```

Replace the database username and password with your local PostgreSQL credentials.

Optional Ollama configuration:

```env
OLLAMA_NUM_PREDICT=1024
OLLAMA_NUM_CTX=8192
```

The project also supports OpenAI configuration through `LLM_PROVIDER`, `OPENAI_API_KEY`, and `OPENAI_MODEL`. Refer to the configuration implementation for the available defaults.

**Security:** Keep `.env` out of version control. Never commit API keys or database credentials.

### 5. Apply database migrations

Ensure PostgreSQL is running and the configured database exists.

```powershell
python -m alembic upgrade head
```

### 6. Start the backend

From the repository root:

```powershell
python -m uvicorn app.main:app --reload
```

Backend:

`http://127.0.0.1:8000`

Interactive API documentation:

`http://127.0.0.1:8000/docs`

Health check:

`http://127.0.0.1:8000/health`

Database readiness:

`http://127.0.0.1:8000/ready`

### 7. Start the frontend

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Vite displays the frontend URL in the terminal, typically:

`http://localhost:5173`

The Vite development proxy forwards `/api` requests to the FastAPI backend.

## Testing

### Backend tests

Activate the Python virtual environment and run:

```powershell
python -m pytest -q -rs
```

Latest verified result:

```text
602 passed, 1 skipped
```

The skipped test is the PostgreSQL integration test, which requires a dedicated test database.

### PostgreSQL integration test

Follow the instructions in [TESTING.md](TESTING.md).

The integration test requires a separate database named `opspilot_test` and the `OPSPILOT_TEST_DATABASE_URL` environment variable.

Never point integration tests at your development or production database.

### Frontend validation

Run linting:

```powershell
cd frontend
npm run lint
```

Build the production frontend:

```powershell
npm run build
```

Both checks have passed in the latest project validation.

## Retrieval Research

OpsPilot includes experimental evaluations of topology-aware evidence retrieval.

The research explores how service relationships can influence evidence ranking and whether topology signals improve the ordering of relevant evidence.

The experimental progression includes:

- Topology-aware retrieval evaluation datasets.
- V2 and V3 retrieval experiments.
- Multiple V3 refinements, including V3.1, V3.2, and V3.3.
- Recall@K, Precision@K, and Mean Reciprocal Rank (MRR) evaluation.
- Comparisons across service-anchored and symptom-only queries.
- Direct and diagnostic relevance perspectives.

The V3.3 evaluation used 20 synthetic scenarios and 260 evidence records.

The strongest tested topology boost candidate improved average MRR from 0.7844 to 0.8594 when compared with the 0.20 boost setting at 0.40 strength. Recall@5 and Precision@5 remained unchanged in that comparison.

These results are limited to the synthetic benchmark. They do not establish production-wide optimality, and the experimental findings have not been treated as a production retrieval configuration change.

Experiment scripts and test cases are preserved in the `experiments/` and `tests/` directories.

## API Capabilities

The backend exposes functionality for:

- Health and readiness checks.
- Incident creation, retrieval, listing, and updates.
- Incident evidence management.
- Evidence analysis.
- Investigation context retrieval.
- AI-assisted investigations.
- Investigation history.
- Structured investigation reports.
- OpenTelemetry trace ingestion and service topology processing.

For exact endpoints, request schemas, and response formats, visit `/docs` while the backend is running.

## Current Project Status

OpsPilot has a functioning full-stack incident investigation workflow, local LLM integration, persistent investigation results, semantic evidence retrieval, and topology-aware retrieval research.

Latest verified validation:

- Backend: 602 tests passed, 1 skipped.
- Frontend: ESLint passed.
- Frontend: TypeScript compilation and Vite production build passed.
- Backend health and readiness checks passed.
- Frontend-to-backend proxy verified.
- AI investigation and persistence verified through the application.

The PostgreSQL integration test remains pending execution against its dedicated test database.

---

**Built as a hands-on exploration of backend engineering, AI-assisted incident investigation, retrieval systems, observability, and reliable software workflows.**