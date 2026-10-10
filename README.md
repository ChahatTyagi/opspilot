
# OpsPilot

Evidence-driven AI incident investigation platform.

OpsPilot aims to help engineers investigate software incidents
by correlating application logs, metrics, traces, deployment changes,
and engineering knowledge.

## Current Features

- FastAPI backend
- Health-check endpoint
- Interactive API documentation
- Automated health-check test

## Tech Stack

- Python
- FastAPI
- Uvicorn
- Pytest

## Run Locally

Create and activate a virtual environment, then install dependencies:

```bash
python -m pip install -r requirements.txt
```

Start the API:

```bash
python -m uvicorn app.main:app --reload
```

API documentation: http://127.0.0.1:8000/docs

## Project Status

Early development. Incident telemetry, retrieval, and AI-powered
investigation features are planned.
