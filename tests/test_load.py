import shutil

import duckdb
import pytest

import load
from conftest import FIXTURES

# Data rows in each fixture file (the reviews file has a multi-line comment,
# so its line count is higher than its row count).
EXPECTED_ROWS = {
    "raw_orders": 28,
    "raw_order_items": 24,
    "raw_order_payments": 27,
    "raw_order_reviews": 26,
    "raw_customers": 27,
    "raw_products": 5,
    "raw_sellers": 3,
    "raw_category_translation": 3,
}

STAGING_OF_RAW = {
    "stg_orders": "raw_orders",
    "stg_order_items": "raw_order_items",
    "stg_payments": "raw_order_payments",
    "stg_reviews": "raw_order_reviews",
    "stg_customers": "raw_customers",
    "stg_products": "raw_products",
    "stg_sellers": "raw_sellers",
}


def scalar(con, sql, params=None):
    return con.execute(sql, params or []).fetchone()[0]


def test_row_counts(fixture_load):
    _, counts = fixture_load
    assert counts == EXPECTED_ROWS


def test_geolocation_not_loaded(con):
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    assert not any("geolocation" in t for t in tables)


@pytest.mark.parametrize("table", list(load.TABLES))
def test_schema_matches_declared_types(con, table):
    _, columns = load.TABLES[table]
    actual = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table],
    ).fetchall()
    assert actual == list(columns.items())


def test_timestamps_parsed(con):
    assert scalar(con, "SELECT order_purchase_timestamp FROM raw_orders WHERE order_id = 'o01' LIMIT 1").isoformat() \
        == "2018-01-01T10:00:00"


def test_zip_prefix_keeps_leading_zero(con):
    assert scalar(con, "SELECT customer_zip_code_prefix FROM raw_customers WHERE customer_id = 'c01'") == "01037"


def test_bom_stripped_from_translation(con):
    assert scalar(con, "SELECT product_category_name_english FROM raw_category_translation "
                       "WHERE product_category_name = 'perfumaria'") == "perfumery"


def test_multiline_quoted_comment(con):
    message = scalar(con, "SELECT review_comment_message FROM raw_order_reviews WHERE review_id = 'r02a'")
    assert message == 'Chegou depois do prazo, "muito" chato.\nSegunda linha do comentario.'


@pytest.mark.parametrize("stg, raw", STAGING_OF_RAW.items())
def test_staging_keeps_every_row(con, stg, raw):
    assert scalar(con, f"SELECT count(*) FROM {stg}") == scalar(con, f"SELECT count(*) FROM {raw}")


@pytest.fixture
def raw_copy(tmp_path):
    """A writable copy of the fixture CSVs for tests that corrupt them."""
    raw = tmp_path / "raw"
    shutil.copytree(FIXTURES, raw)
    return raw


def replace_in(path, old, new):
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")


def test_header_mismatch_fails(raw_copy, tmp_path):
    replace_in(raw_copy / "olist_orders_dataset.csv", '"order_status"', '"status"')
    with pytest.raises(load.LoadError, match="header"):
        load.load(raw_copy, tmp_path / "x.duckdb")


def test_bad_timestamp_fails_instead_of_becoming_null(raw_copy, tmp_path):
    replace_in(raw_copy / "olist_orders_dataset.csv", "2018-01-05 16:00:00", "05/01/2018 16:00")
    with pytest.raises(duckdb.Error):
        load.load(raw_copy, tmp_path / "x.duckdb")


def test_missing_file_fails(raw_copy, tmp_path):
    (raw_copy / "olist_sellers_dataset.csv").unlink()
    with pytest.raises(load.LoadError, match="olist_sellers_dataset.csv"):
        load.load(raw_copy, tmp_path / "x.duckdb")


def test_failed_reload_keeps_previous_database(raw_copy, tmp_path):
    db = tmp_path / "x.duckdb"
    load.load(raw_copy, db)
    replace_in(raw_copy / "olist_sellers_dataset.csv", '"seller_city"', '"city"')
    with pytest.raises(load.LoadError):
        load.load(raw_copy, db)
    with duckdb.connect(str(db), read_only=True) as c:
        assert scalar(c, "SELECT count(*) FROM raw_orders") == EXPECTED_ROWS["raw_orders"]
        assert scalar(c, "SELECT count(*) FROM stg_orders") == EXPECTED_ROWS["raw_orders"]
