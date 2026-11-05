
# OpsPilot

**Evidence-driven AI incident investigation platform**

OpsPilot helps engineers investigate software incidents by organizing incident details and evidence, identifying recurring patterns, retrieving relevant historical context, and generating structured AI-assisted investigation reports.

## Features

- **Incident management** — create, view, update, and track incidents.
- **Evidence collection** — attach incident-specific evidence for investigation.
- **Evidence analysis** — identify patterns and relevant signals in collected evidence.
- **AI-assisted investigations** — generate investigation findings, hypotheses, and confidence assessments.
- **Semantic evidence retrieval** — retrieve relevant evidence to provide additional context for investigations.
- **Structured investigation reports** — combine incident information, analysis, AI findings, and retrieved evidence.
- **API reliability features** — health and database readiness checks, request IDs, and error handling.
- **Web dashboard** — React-based interface for interacting with OpsPilot.

## Tech Stack

### Backend
- Python
- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL
- Pytest

### AI and Retrieval
- OpenAI API
- Semantic evidence retrieval
- Evidence-based investigation reporting

### Frontend
- React
- TypeScript
- Vite

## Project Structure

```text
opspilot/
├── app/                  # FastAPI application and investigation logic
├── migrations/            # Alembic database migrations
├── scripts/               # Supporting scripts
├── tests/                 # Automated tests
├── frontend/               # React + TypeScript dashboard
├── requirements.txt        # Python application dependencies
├── requirements-db.txt     # Database dependencies
├── TESTING.md              # Test and database integration guidance
└── README.md
```

## Prerequisites

- Python
- Node.js and npm
- PostgreSQL
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

### 3. Configure environment variables

Create a `.env` file in the project root.

```env
DATABASE_URL=postgresql+psycopg://<username>:<password>@localhost:5432/<database_name>
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
```

- `DATABASE_URL` is required and must point to your PostgreSQL database.
- `OPENAI_API_KEY` is needed for AI-powered investigation requests.
- `OPENAI_MODEL` selects the model used for AI investigations.

Keep credentials in `.env`. Do not commit this file.

### 4. Apply database migrations

Make sure PostgreSQL is running and the database specified by `DATABASE_URL` exists.

```powershell
python -m alembic upgrade head
```

This applies the database schema migrations.

### 5. Start the backend

```powershell
python -m uvicorn app.main:app --reload
```

Backend API: http://127.0.0.1:8000

Interactive API documentation: http://127.0.0.1:8000/docs

Health endpoint: http://127.0.0.1:8000/health

Database readiness endpoint: http://127.0.0.1:8000/ready

### 6. Start the frontend

Open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Vite will display the local frontend URL in the terminal.

## Testing

Run the standard backend test suite from the project root:

```powershell
python -m pytest -q -rs
```

The PostgreSQL integration test is optional and requires a separate local test database. Follow the safety instructions in [TESTING.md](TESTING.md); do not point integration tests at your development or production database.

Check the frontend build:

```powershell
cd frontend
npm run build
```

Run frontend linting:

```powershell
npm run lint
```

## API Overview

The API supports:

- Health and database readiness checks
- Incident creation, listing, retrieval, and updates
- Incident evidence management
- Evidence analysis
- Investigation context retrieval
- AI-assisted incident investigations
- Structured investigation reports

See the interactive API documentation at `/docs` for available endpoints and request/response schemas.

## Project Status

OpsPilot is an actively developed project focused on building a reliable incident investigation workflow that combines backend systems engineering, evidence processing, semantic retrieval, and AI-assisted analysis.