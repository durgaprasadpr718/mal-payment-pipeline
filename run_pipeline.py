"""
run_pipeline.py - the orchestrator (plain Python, no Airflow/Prefect license).

Flow:  extract -> transform+validate (per squad) -> load (parquet + duckdb)
Writes a run report (compliance, freshness, rejections) for the DQ dashboard.

Run:   python run_pipeline.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.extract import read_csv
from pipeline.load import to_dataframe, write_duckdb, write_parquet
from pipeline.transform import MAPPERS
from pipeline.validate import validate_rows
from schema.canonical import SourceSystem

ROOT = Path(__file__).parent
OUT = ROOT / "output"

SOURCES = {
    SourceSystem.CARDS:         ROOT / "input" / "cards_raw.csv",
    SourceSystem.TRANSFERS:     ROOT / "input" / "transfers_raw.csv",
    SourceSystem.BILL_PAYMENTS: ROOT / "input" / "bill_payments_raw.csv",
}


def main() -> None:
    all_events, report = [], {"run_at": datetime.now(timezone.utc).isoformat(),
                              "sources": {}}

    for source, path in SOURCES.items():
        rows = read_csv(path)
        res = validate_rows(rows, MAPPERS[source], source.value)
        all_events.extend(res.valid)

        report["sources"][source.value] = {
            "rows_in": len(rows),
            "valid": len(res.valid),
            "rejected": len(res.rejected),
            "compliance_rate": round(res.compliance_rate, 4),
            "rejections": [r.__dict__ for r in res.rejected],
        }
        print(f"[{source.value:>20}] {len(res.valid)}/{len(rows)} valid "
              f"({res.compliance_rate:.0%}), {len(res.rejected)} rejected")
        for r in res.rejected[:3]:  # show a sample; full list is in run_report.json
            print(f"    e.g. REJECTED {r.source_event_id}: {r.reason.splitlines()[0]}")
        if len(res.rejected) > 3:
            print(f"    ... and {len(res.rejected) - 3} more (see output/run_report.json)")

    df = to_dataframe(all_events)
    OUT.mkdir(exist_ok=True)
    write_parquet(df, OUT / "payment_events.parquet")
    write_duckdb(df, OUT / "mal.duckdb")

    report["total_events"] = len(df)
    (OUT / "run_report.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"\nWrote {len(df)} canonical events -> output/payment_events.parquet "
          f"+ output/mal.duckdb")


if __name__ == "__main__":
    main()
