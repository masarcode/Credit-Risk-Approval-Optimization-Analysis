"""SQLite database build and SQL-driven portfolio segmentation.

The segmentation results used in the Excel workbook and charts
come from the ``.sql`` files in ``sql/``. An independent pandas
implementation (``python_segments``) exists only to prove the SQL band
logic is correct.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pandas as pd

DB_COLUMNS = [
    "applicant_id", "annual_income", "employment_length", "credit_score", "credit_history_length",
    "number_of_open_accounts", "revolving_utilization", "recent_delinquencies", "recent_credit_inquiries",
    "previous_default_flag", "debt_to_income_ratio", "existing_debt", "requested_loan_amount",
    "observed_default", "employment_length_imputed_flag", "revolving_utilization_imputed_flag",
    "loan_to_income_ratio", "sample", "predicted_pd", "risk_score",
]

# Maps the SQL "dimension" label to the config key and source column
DIMENSIONS = {
    "Credit score": ("credit_score_band", "credit_score"),
    "Income": ("income_band", "annual_income"),
    "Debt-to-income": ("dti_band", "debt_to_income_ratio"),
    "Card utilization": ("utilization_band", "revolving_utilization"),
    "Recent delinquencies": ("delinquency_band", "recent_delinquencies"),
    "Loan size": ("loan_size_band", "requested_loan_amount"),
}


def read_named_queries(path: Path) -> dict[str, str]:
    """Split a .sql file on '-- name: <query_name>' markers."""
    text = Path(path).read_text(encoding="utf-8")
    parts = re.split(r"^--\s*name:\s*(\w+)\s*$", text, flags=re.MULTILINE)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def build_database(df: pd.DataFrame, db_path: Path, sql_dir: Path, thresholds: list[int]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        conn.executescript((sql_dir / "create_tables.sql").read_text(encoding="utf-8"))
        # Append into the table defined by create_tables.sql so its types and
        # CHECK constraints apply to every row loaded
        df[DB_COLUMNS].to_sql("applicants", conn, if_exists="append", index=False, chunksize=10_000)
        conn.executemany(
            "INSERT INTO scenario_thresholds (scenario_id, threshold) VALUES (?, ?)",
            [(f"S{i + 1:02d}", int(t)) for i, t in enumerate(thresholds)],
        )
        conn.commit()


def run_sql_file(db_path: Path, sql_path: Path, params: dict | None = None) -> dict[str, pd.DataFrame]:
    queries = read_named_queries(sql_path)
    with sqlite3.connect(db_path) as conn:
        return {name: pd.read_sql_query(q, conn, params=params or {}) for name, q in queries.items()}


def python_segments(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Independent pandas version of the SQL band counts (for reconciliation only)."""
    frames = []
    for dimension, (key, col) in DIMENSIONS.items():
        spec = config["segments"][key]
        band = pd.cut(df[col], bins=spec["edges"], labels=spec["labels"], right=False)
        g = (df.assign(band=band.astype(str))
             .groupby("band", observed=True)["observed_default"]
             .agg(applicants="size", defaults="sum").reset_index())
        g.insert(0, "dimension", dimension)
        frames.append(g)
    return pd.concat(frames, ignore_index=True)
