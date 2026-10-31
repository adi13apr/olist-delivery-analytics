from pathlib import Path

import duckdb
import pytest

import load

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def fixture_load(tmp_path_factory):
    """Load the synthetic fixture once per session; returns (db path, row counts)."""
    db = tmp_path_factory.mktemp("db") / "fixture.duckdb"
    counts = load.load(FIXTURES, db)
    return db, counts


@pytest.fixture
def con(fixture_load):
    db, _ = fixture_load
    with duckdb.connect(str(db), read_only=True) as c:
        yield c
