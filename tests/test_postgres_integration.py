import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db_models import IncidentRecord


DATABASE_URL = os.getenv("OPSPILOT_TEST_DATABASE_URL")

if not DATABASE_URL:
    pytest.skip(
        "Set OPSPILOT_TEST_DATABASE_URL to run PostgreSQL integration tests",
        allow_module_level=True,
    )

url = make_url(DATABASE_URL)

if (
    url.get_backend_name() != "postgresql"
    or url.database != "opspilot_test"
    or url.host not in ("localhost", "127.0.0.1", "::1")
):
    raise RuntimeError(
        "Integration tests require the local opspilot_test PostgreSQL database"
    )

test_engine = create_engine(DATABASE_URL)
TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    expire_on_commit=False,
)


def test_incident_persists_across_sessions():
    unique_title = f"Integration test {uuid4()}"
    incident_id = None
    try:
        with TestSessionLocal() as session:
            incident = IncidentRecord(
                title=unique_title,
                description="Verify PostgreSQL persistence",
                service="integration-test",
                environment="test",
                severity="low",
            )
            session.add(incident)
            session.commit()
            incident_id = incident.id

        # A new session proves the record was committed to PostgreSQL.
        with TestSessionLocal() as session:
            saved_incident = session.scalar(
                select(IncidentRecord).where(
                    IncidentRecord.id == incident_id
                )
            )

            assert saved_incident is not None
            assert saved_incident.title == unique_title
            assert saved_incident.service == "integration-test"
            assert saved_incident.environment == "test"
            assert saved_incident.status == "open"
            assert saved_incident.created_at is not None

    finally:
        if incident_id is not None:
            with TestSessionLocal() as session:
                incident_to_delete = session.get(
                    IncidentRecord,
                    incident_id,
                )

                if incident_to_delete is not None:
                    session.delete(incident_to_delete)
                    session.commit()

        test_engine.dispose()