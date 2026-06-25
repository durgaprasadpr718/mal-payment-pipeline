# Mal Unified Payment Data Pipeline

A canonical payment data model and ingestion pipeline that unifies three product
squads (Cards, Transfers, Bill Payments) at Mal, a UAE-based multi-product Islamic
neobank.

Built entirely with free, open-source, license-free tools: Python, Pydantic,
DuckDB, Parquet, Streamlit, Plotly. No warehouse account, no orchestration license.
Runs on any laptop.

| Brief requirement | Where it lives |
|---|---|
| Canonical payment event schema | `schema/canonical.py` |
| Python ingestion pipeline (extract, transform, validate, load) | `pipeline/`, `run_pipeline.py` |
| Three mock CSVs in three different squad formats | `input/` (produced by `generate_data.py`) |
| Schema validation with error handling | `pipeline/validate.py` |
| Data contract versioning (v1 to v2 migration) | `schema/versioning.py` |
| Downstream SQL queries | `queries/analytics.sql` |
| Architecture and migration strategy (Part 2) | `docs/architecture_strategy.md` |
| Data quality dashboard (Part 3 bonus) | `dashboard/app.py` |

## Why these tools (the free stack)

| Paid or enterprise thing | Free replacement used here |
|---|---|
| Snowflake or BigQuery | DuckDB, an embedded zero-server SQL warehouse in a file |
| Airflow, Prefect, Dagster | plain Python orchestrator (`run_pipeline.py`) |
| Great Expectations or paid DQ | Pydantic contract plus a Streamlit dashboard |
| Looker or Tableau | Streamlit and Plotly (free deploy on Streamlit Community Cloud) |
| Paid hosting | GitHub plus Streamlit Community Cloud (both free) |

## How the data flows

```
generate_data.py  ->  input/*.csv  ->  run_pipeline.py  ->  output/  ->  dashboard + queries
   (synthetic)        (raw feeds)      (extract,           (parquet +     (Streamlit / DuckDB)
                                        transform,          duckdb +
                                        validate, load)     report)
```

## Setup

```bash
git clone <your-repo-url>
cd mal-payment-pipeline
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Requires Python 3.9+. After activating the venv, plain `pip` and `python` work
(no need for the `3`).

## Step 1: generate input data

```bash
python generate_data.py                                   # 5,000 rows over 30 days
python generate_data.py --rows 20000 --days 45 --bad-rate 0.03 --seed 7
```

Writes the three squad CSVs into `input/`. The data bakes in UAE realism (AED plus
FX, merchants like Carrefour and Noon, billers like DEWA and SALIK) and
deliberately injects a small fraction of bad rows, one low-volume anomaly day, and
a few empty customer ids, so the compliance metric and the dashboard anomaly
detection have something real to show.

## Step 2: run the pipeline

```bash
python run_pipeline.py
```

Reads `input/`, transforms to the canonical schema, validates each row
(quarantining bad ones with a reason), and writes to `output/`:

- `payment_events.parquet`, the canonical data lake file
- `mal.duckdb`, the queryable warehouse
- `run_report.json`, the compliance, freshness, and rejection report

## Step 3: query the unified model

```bash
duckdb output/mal.duckdb < queries/analytics.sql
```

Six example queries: daily volume by type, success rate by source, customer 360
cross-product spend, currency mix, Shariah-compliance audit, failed or reversed
payments.

## Step 4: run the data quality dashboard

```bash
streamlit run dashboard/app.py
```

Shows headline KPIs, schema compliance per source, data freshness, and anomaly
detection (volume drop vs rolling baseline, null-rate alerts). A static preview
of the layout is in `docs/dashboard_preview.png`.

## Try the versioning migration

```bash
python -m schema.versioning      # prints a v1 record upgraded to the v2 contract
```

## Deploy a free demo

- Dashboard: push this repo to GitHub, then on share.streamlit.io point a new app
  at `dashboard/app.py`. Free, public URL, no card required. Commit `input/` (and
  optionally `output/`) so the demo has data, or have the app run the pipeline on
  start.
- Repo and docs: GitHub renders `docs/architecture_strategy.md` directly.

## Project structure

```
mal-payment-pipeline/
├── schema/          canonical.py (the contract) + versioning.py (v1 to v2)
├── input/           three squad CSVs, three different formats
├── pipeline/        extract / transform / validate / load
├── queries/         analytics.sql, downstream queries on the unified model
├── dashboard/       app.py, Streamlit + Plotly DQ dashboard
├── docs/            architecture_strategy.md, Part 2
├── generate_data.py synthetic data generator (writes to input/)
└── run_pipeline.py  orchestrator (plain Python)
```
