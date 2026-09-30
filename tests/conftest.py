"""Shared pytest fixtures.

IMPORTANT: These fixtures deliberately DO NOT use ``db.local_db`` because
importing that module opens (and creates) the *production* SQLite file at
``C:\\ProgramData\\FishManagement\\fish.db``. Tests instead build an isolated
in-memory database directly from the ORM models, so no test ever touches
real data. See tests/test_db_integration.py.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db.models import Base


@pytest.fixture
def engine():
    """A fresh, isolated in-memory SQLite database per test.

    Mirrors production by enabling ``PRAGMA foreign_keys`` (db.local_db sets
    the same on its engine), so integration tests validate against identical
    referential-integrity constraints.
    """
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # keep the same in-memory DB across connections
    )

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture
def db_session(engine):
    """An ORM session bound to the isolated database; rolled back after use."""
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
