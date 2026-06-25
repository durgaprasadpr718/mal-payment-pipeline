"""
Load step: write canonical events to Parquet (the lake file) and register them
in a DuckDB database file (the warehouse downstream teams query). Both are free
and file-based: no server, no license, runs anywhere.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from schema.canonical import PaymentEvent


def to_dataframe(events: list[PaymentEvent]) -> pd.DataFrame:
    return pd.DataFrame([e.to_row() for e in events])


def write_parquet(df: pd.DataFrame, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def write_duckdb(df: pd.DataFrame, db_path: str | Path,
                 table: str = "payment_events") -> None:
    con = duckdb.connect(str(db_path))
    con.register("incoming", df)
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM incoming")
    con.close()
