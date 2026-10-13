from app import database


def test_get_db_closes_session(monkeypatch):
    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    fake_session = FakeSession()

    monkeypatch.setattr(
        database,
        "SessionLocal",
        lambda: fake_session,
    )

    db_generator = database.get_db()

    yielded_db = next(db_generator)
    assert yielded_db is fake_session
    assert fake_session.closed is False

    db_generator.close()

    assert fake_session.closed is True

def test_get_db_closes_session_after_exception(monkeypatch):
    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    fake_session = FakeSession()

    monkeypatch.setattr(
        database,
        "SessionLocal",
        lambda: fake_session,
    )

    db_generator = database.get_db()
    next(db_generator)

    try:
        db_generator.throw(RuntimeError("Simulated failure"))
    except RuntimeError:
        pass

    assert fake_session.closed is True