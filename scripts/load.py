"""Load the Olist CSVs into DuckDB as raw_ tables and build the staging views.

Every column has an explicit type, so the real data and the test fixtures get
the same schema (DuckDB's type sniffing would read zip prefixes such as
"01037" as integers, and an all-empty fixture column as VARCHAR).

The load never drops rows silently: it fails if a CSV header differs from the
expected schema, if a timestamp does not parse, or if DuckDB reads a different
number of rows than Python's csv module counts in the file.

Usage:
    python scripts/load.py [--raw-dir data/raw] [--db olist.duckdb]
"""

import argparse
import csv
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
STAGING_SQL = ROOT / "sql" / "01_staging.sql"
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

TS = "TIMESTAMP"
VC = "VARCHAR"
INT = "INTEGER"
MONEY = "DECIMAL(10,2)"

# raw table -> (CSV file name, ordered {column: type}).
# olist_geolocation_dataset.csv is deliberately not loaded.
TABLES = {
    "raw_orders": ("olist_orders_dataset.csv", {
        "order_id": VC,
        "customer_id": VC,
        "order_status": VC,
        "order_purchase_timestamp": TS,
        "order_approved_at": TS,
        "order_delivered_carrier_date": TS,
        "order_delivered_customer_date": TS,
        "order_estimated_delivery_date": TS,
    }),
    "raw_order_items": ("olist_order_items_dataset.csv", {
        "order_id": VC,
        "order_item_id": INT,
        "product_id": VC,
        "seller_id": VC,
        "shipping_limit_date": TS,
        "price": MONEY,
        "freight_value": MONEY,
    }),
    "raw_order_payments": ("olist_order_payments_dataset.csv", {
        "order_id": VC,
        "payment_sequential": INT,
        "payment_type": VC,
        "payment_installments": INT,
        "payment_value": MONEY,
    }),
    "raw_order_reviews": ("olist_order_reviews_dataset.csv", {
        "review_id": VC,
        "order_id": VC,
        "review_score": INT,
        "review_comment_title": VC,
        "review_comment_message": VC,
        "review_creation_date": TS,
        "review_answer_timestamp": TS,
    }),
    "raw_customers": ("olist_customers_dataset.csv", {
        "customer_id": VC,
        "customer_unique_id": VC,
        "customer_zip_code_prefix": VC,
        "customer_city": VC,
        "customer_state": VC,
    }),
    "raw_products": ("olist_products_dataset.csv", {
        "product_id": VC,
        "product_category_name": VC,
        # Misspelled in the source; renamed in stg_products.
        "product_name_lenght": INT,
        "product_description_lenght": INT,
        "product_photos_qty": INT,
        "product_weight_g": INT,
        "product_length_cm": INT,
        "product_height_cm": INT,
        "product_width_cm": INT,
    }),
    "raw_sellers": ("olist_sellers_dataset.csv", {
        "seller_id": VC,
        "seller_zip_code_prefix": VC,
        "seller_city": VC,
        "seller_state": VC,
    }),
    "raw_category_translation": ("product_category_name_translation.csv", {
        "product_category_name": VC,
        "product_category_name_english": VC,
    }),
}


class LoadError(Exception):
    pass


def sql_str(value):
    return "'" + str(value).replace("'", "''") + "'"


def inspect_csv(path):
    """Return (header, record count) using the csv module as an independent count."""
    # utf-8-sig strips the BOM that product_category_name_translation.csv starts with.
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        records = sum(1 for row in reader if row)
    return header, records


def load_table(con, table, path, columns):
    header, expected = inspect_csv(path)
    if header != list(columns):
        raise LoadError(
            f"{path.name}: header {header} does not match expected columns {list(columns)}"
        )

    columns_sql = "{" + ", ".join(f"{sql_str(c)}: {sql_str(t)}" for c, t in columns.items()) + "}"
    con.execute(f"""
        CREATE OR REPLACE TABLE {table} AS
        SELECT * FROM read_csv(
            {sql_str(path.as_posix())},
            header = true,
            auto_detect = false,
            delim = ',',
            quote = '"',
            escape = '"',
            columns = {columns_sql},
            timestampformat = {sql_str(TIMESTAMP_FORMAT)},
            encoding = 'utf-8'
        )
    """)

    loaded = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    if loaded != expected:
        raise LoadError(f"{path.name}: csv module counts {expected} rows but DuckDB loaded {loaded}")
    return loaded


def build_staging(con):
    con.execute(STAGING_SQL.read_text(encoding="utf-8"))


def load(raw_dir, db_path):
    """Load every raw table, build the staging views and return {table: row count}."""
    raw_dir = Path(raw_dir)
    missing = [f for f, _ in TABLES.values() if not (raw_dir / f).exists()]
    if missing:
        raise LoadError(f"missing CSV files in {raw_dir}: {', '.join(missing)}")

    # One transaction: a failed load leaves the previous database untouched.
    counts = {}
    with duckdb.connect(str(db_path)) as con:
        con.begin()
        try:
            for table, (file_name, columns) in TABLES.items():
                counts[table] = load_table(con, table, raw_dir / file_name, columns)
            build_staging(con)
        except Exception:
            con.rollback()
            raise
        con.commit()
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-dir", default=ROOT / "data" / "raw", type=Path)
    parser.add_argument("--db", default=ROOT / "olist.duckdb", type=Path)
    args = parser.parse_args(argv)

    try:
        counts = load(args.raw_dir, args.db)
    except (LoadError, duckdb.Error) as e:
        print(f"Load failed: {e}", file=sys.stderr)
        return 1

    width = max(len(t) for t in counts)
    print(f"Loaded into {args.db}")
    for table, n in counts.items():
        print(f"  {table:<{width}}  {n:>9,}")
    print("Skipped: olist_geolocation_dataset.csv (not needed for delivery analysis)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
