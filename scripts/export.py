"""Run every analysis query against olist.duckdb and write CSVs for Google Sheets.

Each sql/analysis/<name>.sql becomes data/exports/<name>.csv, plus
09b_black_friday_significance.csv from scripts/significance.py. Queries run in
file order, and each is also registered as a temporary view a<name> (e.g.
a02_wow_delivery_by_state) so a later query can build on an earlier one.

Sheets-friendly output: UTF-8 without BOM, LF line endings, a header row, no
index column, ISO dates, TRUE/FALSE booleans, empty cells for NULL. Numbers are
rounded in the SQL. An export over MAX_ROWS rows fails the run, because these
files are meant to be aggregates.

Usage:
    python scripts/export.py [--db olist.duckdb] [--out-dir data/exports]
"""

import argparse
import csv
import datetime
import decimal
import math
import sys
from pathlib import Path

import duckdb

import significance

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "sql" / "analysis"
EXPORT_DIR = ROOT / "data" / "exports"
SIGNIFICANCE_NAME = "09b_black_friday_significance"
MAX_ROWS = 5000


class ExportError(Exception):
    pass


def analysis_files():
    return sorted(ANALYSIS_DIR.glob("*.sql"))


def view_name(path):
    return f"a{path.stem}"


def run_analyses(con):
    """Run every analysis query in order; return {name: (columns, rows)}."""
    results = {}
    for path in analysis_files():
        sql = path.read_text(encoding="utf-8").strip().rstrip(";")
        con.execute(f"CREATE OR REPLACE TEMP VIEW {view_name(path)} AS {sql}")
        cursor = con.execute(sql)
        results[path.stem] = ([d[0] for d in cursor.description], cursor.fetchall())
    results[SIGNIFICANCE_NAME] = significance.black_friday_test(con)
    return results


def format_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat(sep=" ") if isinstance(value, datetime.datetime) else value.isoformat()
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        # Plain decimal notation (no 1e-05); the SQL already rounded the value.
        return f"{value:.10f}".rstrip("0").rstrip(".")
    if isinstance(value, decimal.Decimal):
        return format(value, "f")
    return str(value)


def write_csv(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows([format_value(v) for v in row] for row in rows)


def export_all(con, out_dir):
    """Write every export to out_dir; return {file name: row count}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = run_analyses(con)
    too_big = {name: len(rows) for name, (_, rows) in results.items() if len(rows) > MAX_ROWS}
    if too_big:
        raise ExportError(f"exports over {MAX_ROWS} rows (not aggregated?): {too_big}")
    written = {}
    for name, (columns, rows) in results.items():
        write_csv(out_dir / f"{name}.csv", columns, rows)
        written[f"{name}.csv"] = len(rows)
    return written


def excluded_months(con):
    return [
        (month.isoformat()[:7], orders, reason)
        for month, orders, reason in con.execute(
            "SELECT month, orders, exclusion_reason FROM int_months WHERE NOT is_trend_month ORDER BY month"
        ).fetchall()
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=ROOT / "olist.duckdb", type=Path)
    parser.add_argument("--out-dir", default=EXPORT_DIR, type=Path)
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(f"{args.db} not found; run scripts/load.py first.", file=sys.stderr)
        return 1
    try:
        with duckdb.connect(str(args.db), read_only=True) as con:
            written = export_all(con, args.out_dir)
            excluded = excluded_months(con)
    except (ExportError, duckdb.Error, ValueError) as e:
        print(f"Export failed: {e}", file=sys.stderr)
        return 1

    width = max(len(n) for n in written)
    print(f"Wrote {len(written)} files to {args.out_dir}")
    for name, n in written.items():
        print(f"  {name:<{width}}  {n:>5,} rows")
    print("Months excluded from trend views:")
    for month, orders, reason in excluded:
        print(f"  {month}  {orders:>6,} orders  {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
