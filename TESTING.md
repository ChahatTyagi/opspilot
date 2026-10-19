# Testing OpsPilot

## 1. Run the standard test suite

Activate the virtual environment and run:

```powershell
python -m pytest -q -rs
```

The PostgreSQL integration test is skipped when `OPSPILOT_TEST_DATABASE_URL` is not configured. Check the test summary to confirm which tests ran.

## 2. Run the PostgreSQL integration test

The integration test requires a local PostgreSQL database named `opspilot_test` with the latest Alembic migrations applied.

Run the test using a temporary `OPSPILOT_TEST_DATABASE_URL` environment variable. Do not commit database credentials or put passwords in source code.

The test verifies that an incident committed in one session can be retrieved from a separate session. It removes the test record it creates.

## 3. Database safety

- Integration tests must use the local `opspilot_test` database.
- Never point integration tests at the main `opspilot` database or a production database.
- Keep database credentials out of Git.
- Apply migrations to the test database before running integration tests.
