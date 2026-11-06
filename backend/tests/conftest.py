"""Shared pytest setup.

Backend modules import each other as top-level modules (e.g. `import financial_engine`),
so put backend/ on sys.path. Tests need no server, no network and no GROQ_API_KEY.
"""
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(autouse=True)
def temp_db():
    """Every test gets its own empty in-memory SQLite DB; the real backend/gritos.db is never touched."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import db
    import main

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db.init_db(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    main.app.dependency_overrides[db.get_db] = override
    yield Session
    main.app.dependency_overrides.pop(db.get_db, None)
    engine.dispose()


@pytest.fixture(autouse=True)
def no_real_llm(monkeypatch):
    """Guarantee no test reaches Groq, even if a local .env provides a key.
    Tests that exercise the LLM path install their own fake client."""
    import llm_advisor
    monkeypatch.setattr(llm_advisor, "client", None)
