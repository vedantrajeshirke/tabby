import os
import uuid

import pytest

from core import db

# Matches the database started by `docker compose up db`. Local test credentials only.
DEFAULT_TEST_DB = "host=localhost port=5433 dbname=snapspend user=snapspend password=snapspend"


@pytest.fixture
def conn():
    """A real Postgres connection, in a private schema that's dropped after the test."""
    try:
        connection = db.connect(os.getenv("TEST_DATABASE_URL", DEFAULT_TEST_DB))
    except Exception:
        pytest.fail("Postgres isn't reachable. Start it with: docker compose up -d db", pytrace=False)
    schema = f"test_{uuid.uuid4().hex}"
    connection.execute(f"CREATE SCHEMA {schema}")
    connection.execute(f"SET search_path TO {schema}")
    db.init_db(connection)
    yield connection
    connection.execute("RESET ROLE")
    connection.execute(f"DROP SCHEMA {schema} CASCADE")
    connection.close()
