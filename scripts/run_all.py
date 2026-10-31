"""Rebuild everything in order: load the CSVs, write DATA_QUALITY.md, write the exports.

Stops at the first step that fails. To refresh the Google Sheets dashboard,
run this, then commit and push data/exports/.

Usage:
    python scripts/run_all.py
"""

import sys

import export
import load
import quality_report

STEPS = [
    ("Load data/raw into olist.duckdb", load.main),
    ("Write DATA_QUALITY.md", quality_report.main),
    ("Write data/exports/", export.main),
]


def main():
    for i, (title, step) in enumerate(STEPS, start=1):
        print(f"\n[{i}/{len(STEPS)}] {title}")
        code = step([])
        if code != 0:
            print(f"\nStopped: step {i} ({title}) failed.", file=sys.stderr)
            return code
    print("\nDone. Commit and push data/exports/ to refresh the dashboard.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
