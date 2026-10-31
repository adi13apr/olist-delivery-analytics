# olist-delivery-analytics

SQL analysis of delivery performance in the Olist Brazilian e-commerce dataset,
approached the way a quick-commerce operations analyst would: how long orders
take, how often the delivery promise is missed, and which data can be trusted
to answer that.

Stack: Python 3.13, DuckDB, pytest, GitHub Actions.

## Layout

```
data/raw/            Olist CSVs (gitignored, never committed)
data/exports/        Aggregated CSVs for Google Sheets (committed; filled in Phase 2)
scripts/load.py      Loads the CSVs into olist.duckdb as raw_ tables, builds staging views
scripts/checks.py    Registry of data-quality checks and the decision for each
scripts/quality_report.py   Runs the checks on the full data and writes DATA_QUALITY.md
sql/01_staging.sql   Staging views (stg_*)
sql/checks/          One SQL file per data-quality check
tests/               pytest suite, run against tests/fixtures/ (synthetic data)
DATA_QUALITY.md      Generated: real counts for every check, and the decision taken
```

## Setup and run (Windows PowerShell)

From the repository root, with the Olist CSVs in `data/raw/`:

```powershell
# 1. Create the virtual environment and install dependencies
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Load the data into olist.duckdb (prints row counts per table)
.\.venv\Scripts\python.exe scripts\load.py

# 3. Run the tests (synthetic fixture; does not need data/raw)
.\.venv\Scripts\python.exe -m pytest

# 4. Regenerate DATA_QUALITY.md from the full data
.\.venv\Scripts\python.exe scripts\quality_report.py
```

Calling `.venv\Scripts\python.exe` directly avoids PowerShell's script execution
policy. To activate the venv instead, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then
`.\.venv\Scripts\Activate.ps1`.

## Loading

`scripts/load.py` loads every Olist CSV except `olist_geolocation_dataset.csv`.
Every column has an explicitly declared type rather than a guessed one; guessing
would turn zip prefixes such as `01037` into the integer `1037`. Timestamps are
parsed as `%Y-%m-%d %H:%M:%S`.

The loader never drops rows silently. It fails, and leaves any previous
database untouched, if:

- a CSV header differs from the expected columns,
- a timestamp does not parse (it never becomes NULL), or
- DuckDB loads a different number of rows than Python's `csv` module counts in the file.

## Delivery metrics

`stg_orders` keeps every order and adds:

| Column | Definition |
|---|---|
| `delivery_days` | Purchase timestamp to customer delivery timestamp, in **fractional days rounded to 2 decimals** (e.g. 4 days 6 hours = 4.25). |
| `estimated_days` | Purchase timestamp to the estimated delivery date, same unit. |
| `is_late` | Delivered on a **later calendar date** than the estimated date: `delivered::DATE > estimated::DATE`. |
| `exclusion_reason` | NULL when the order is eligible for delivery metrics; otherwise why it is not. |
| `is_delivery_metric_eligible` | `exclusion_reason IS NULL`. |

The three metrics are filled only for eligible orders, so an aggregate over
`stg_orders` cannot accidentally include a bad row.

**Why `is_late` compares dates.** Olist stores every estimated delivery date at
`00:00:00`, so it is a date, not a deadline with a time. Comparing timestamps
would mark any order delivered during the promised day as late. On the full
data, a timestamp comparison flags 7,826 late orders, while the date comparison
flags 6,534. The difference is 1,292 orders delivered on the promised day.

**Why fractional days.** Whole-day counts round a 25-hour delivery and a
47-hour delivery to the same number. Fractional days keep that difference for
averages and percentiles. Two decimals is about 15 minutes of precision.

**Exclusions.** Only delivered orders with valid dates count. Every other order
gets exactly one reason (first match wins): `duplicate_order_id`,
`status_not_delivered`, `missing_purchase_date`, `missing_delivered_date`,
`missing_estimated_date`, `delivered_before_purchase`.
`stg_delivery_exclusions` counts orders per reason. `v_delivery_reconciliation`
checks that raw rows = staged rows = eligible + excluded.

## Data quality

See [DATA_QUALITY.md](DATA_QUALITY.md) for the real count of every check and the
decision taken for each issue. Each check is a SQL file in `sql/checks/`. The
tests run the same SQL against `tests/fixtures/`, a small synthetic copy of the
schema with at least one deliberately bad row for each check, and assert the
exact number of bad rows found.

## CI

GitHub Actions installs `requirements.txt` and runs `pytest`. CI never sees the
raw data; everything it tests comes from `tests/fixtures/`.

## Data

Data: Brazilian E-Commerce Public Dataset by Olist (Kaggle), CC BY-NC-SA 4.0.
Raw data is not included in this repo.
