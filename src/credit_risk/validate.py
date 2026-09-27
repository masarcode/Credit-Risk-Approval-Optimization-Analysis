"""Data and results validation checks.

Each check returns a record (stage, check, passed, detail). The pipeline
collects them into ``outputs/tables/validation_report.csv`` and stops if
any check fails. The pytest suite re-runs the same functions, so a failing
check fails the tests too.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class Check:
    stage: str
    check: str
    passed: bool
    detail: str


def _check(stage: str, name: str, condition: bool, detail: str = "") -> Check:
    return Check(stage, name, bool(condition), detail)


def to_frame(checks: list[Check]) -> pd.DataFrame:
    return pd.DataFrame([asdict(c) for c in checks])


# ---------------------------------------------------------------------------
# Raw and clean data
# ---------------------------------------------------------------------------
def validate_raw(raw: pd.DataFrame, config: dict) -> list[Check]:
    n = config["project"]["n_applicants"]
    dupes = config["raw_data_issues"]["duplicate_rows"]
    return [
        _check("raw", "raw row count = applicants + injected duplicates",
               len(raw) == n + dupes, f"{len(raw):,} rows"),
        _check("raw", "raw file contains the expected missing values",
               raw["employment_length"].isna().any() and raw["revolving_utilization"].isna().any(),
               f"{int(raw.isna().sum().sum()):,} missing cells"),
    ]


def validate_clean(df: pd.DataFrame, config: dict) -> list[Check]:
    b = config["bounds"]
    n = config["project"]["n_applicants"]
    s = "clean"
    lo, hi = b["credit_score"]
    checks = [
        _check(s, f"exactly {n:,} records", len(df) == n, f"{len(df):,} rows"),
        _check(s, "applicant_id is unique", df["applicant_id"].is_unique,
               f"{df['applicant_id'].nunique():,} unique ids"),
        _check(s, "no missing values in any column", not df.isna().any().any(),
               f"{int(df.isna().sum().sum())} missing cells"),
        _check(s, f"credit_score within [{lo}, {hi}]",
               df["credit_score"].between(lo, hi).all(),
               f"min {df['credit_score'].min()}, max {df['credit_score'].max()}"),
    ]
    for col in ["debt_to_income_ratio", "revolving_utilization", "annual_income", "requested_loan_amount"]:
        lo, hi = b[col]
        checks.append(_check(s, f"{col} within [{lo}, {hi}]", df[col].between(lo, hi).all(),
                             f"min {df[col].min():,.4g}, max {df[col].max():,.4g}"))
    non_negative = ["existing_debt", "employment_length", "credit_history_length",
                    "number_of_open_accounts", "recent_delinquencies", "recent_credit_inquiries"]
    checks.append(_check(s, "count and amount fields are non-negative",
                         (df[non_negative] >= 0).all().all(), ", ".join(non_negative)))
    for col in ["observed_default", "previous_default_flag"]:
        checks.append(_check(s, f"{col} is binary 0/1", set(df[col].unique()) <= {0, 1},
                             f"values {sorted(df[col].unique().tolist())}"))
    rate = df["observed_default"].mean()
    checks.append(_check(s, "overall default rate is plausible (2% to 30%)", 0.02 <= rate <= 0.30,
                         f"{rate:.2%}"))
    # Direction checks: the relationships the simulation is designed to have
    corr = df[["credit_score", "debt_to_income_ratio", "revolving_utilization",
               "recent_delinquencies", "observed_default"]].corr()["observed_default"]
    checks.append(_check(s, "default rises as credit score falls", corr["credit_score"] < 0,
                         f"corr {corr['credit_score']:.3f}"))
    for col in ["debt_to_income_ratio", "revolving_utilization", "recent_delinquencies"]:
        checks.append(_check(s, f"default rises with {col}", corr[col] > 0, f"corr {corr[col]:.3f}"))
    return checks


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------
def _score_is_monotonic(df: pd.DataFrame) -> bool:
    """Every applicant at a higher score has a lower PD than every applicant at a lower score."""
    g = df.groupby("risk_score")["predicted_pd"].agg(["min", "max"]).sort_index()
    return bool((g["max"].to_numpy()[1:] <= g["min"].to_numpy()[:-1]).all())


def validate_scored(df: pd.DataFrame, model_summary: dict) -> list[Check]:
    s = "score"
    return [
        _check(s, "every applicant has a score and PD", df[["risk_score", "predicted_pd"]].notna().all().all()),
        _check(s, "predicted PD strictly between 0 and 1",
               df["predicted_pd"].between(0, 1, inclusive="neither").all()),
        _check(s, "higher score always means lower predicted PD",
               _score_is_monotonic(df)),
        _check(s, "holdout AUC above 0.70 (useful rank-ordering)",
               model_summary["auc_holdout"] > 0.70, f"AUC {model_summary['auc_holdout']:.3f}"),
        _check(s, "no material overfitting (dev AUC - holdout AUC < 0.02)",
               model_summary["auc_development"] - model_summary["auc_holdout"] < 0.02,
               f"dev {model_summary['auc_development']:.3f} vs holdout {model_summary['auc_holdout']:.3f}"),
        _check(s, "holdout calibration: predicted vs observed default rate within 1 point",
               abs(model_summary["holdout_mean_pd"] - model_summary["holdout_default_rate"]) < 0.01,
               f"predicted {model_summary['holdout_mean_pd']:.2%} vs observed {model_summary['holdout_default_rate']:.2%}"),
    ]


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
def validate_scenarios(scen: pd.DataFrame, df: pd.DataFrame, config: dict) -> list[Check]:
    s = "scenarios"
    base = config["scenarios"]["baseline_threshold"]
    checks = [
        _check(s, f"{config['scenarios']['count']} scenarios produced",
               len(scen) == config["scenarios"]["count"], f"{len(scen)} rows"),
        _check(s, "first scenario is the baseline threshold",
               scen.iloc[0]["threshold"] == base and scen.iloc[0]["is_baseline"]),
        _check(s, "approval rate falls as the threshold tightens",
               scen["approval_rate"].is_monotonic_decreasing and scen["approval_rate"].is_unique),
        _check(s, "approved defaults never increase as the threshold tightens",
               scen["approved_defaults"].is_monotonic_decreasing),
        _check(s, "baseline changes are exactly zero",
               scen.iloc[0]["pct_change_approvals"] == 0 and scen.iloc[0]["pct_change_defaults"] == 0),
    ]
    # Reconcile every scenario to a direct count from the applicant table
    ok = True
    for _, row in scen.iterrows():
        approved = df["risk_score"] >= row["threshold"]
        ok &= int(approved.sum()) == row["approved"]
        ok &= int(df.loc[approved, "observed_default"].sum()) == row["approved_defaults"]
        ok &= int(row["approved"] + row["declined"]) == len(df)
    checks.append(_check(s, "every scenario reconciles to the applicant-level data", ok))
    return checks


def validate_sql_reconciliation(sql_scen: pd.DataFrame, py_scen: pd.DataFrame,
                                sql_segments: pd.DataFrame, df: pd.DataFrame) -> list[Check]:
    s = "sql"
    merged = py_scen.merge(sql_scen, on="threshold", suffixes=("_py", "_sql"))
    same_counts = (
        len(merged) == len(py_scen)
        and (merged["approved_py"] == merged["approved_sql"]).all()
        and (merged["approved_defaults_py"] == merged["approved_defaults_sql"]).all()
        and np.allclose(merged["approved_loan_volume_py"], merged["approved_loan_volume_sql"])
    )
    checks = [_check(s, "SQL scenario results match Python scenario results", same_counts,
                     f"{len(merged)} thresholds compared")]
    n, d = len(df), int(df["observed_default"].sum())
    for dim, grp in sql_segments.groupby("dimension"):
        checks.append(_check(s, f"SQL {dim} segments sum to all applicants and defaults",
                             grp["applicants"].sum() == n and grp["defaults"].sum() == d,
                             f"{grp['applicants'].sum():,} applicants, {grp['defaults'].sum():,} defaults"))
    return checks


def validate_segment_parity(sql_segments: pd.DataFrame, py_segments: pd.DataFrame) -> list[Check]:
    """SQL band definitions must match the Python band definitions exactly."""
    m = sql_segments.merge(py_segments, on=["dimension", "band"], suffixes=("_sql", "_py"))
    ok = (len(m) == len(sql_segments) == len(py_segments)
          and (m["applicants_sql"] == m["applicants_py"]).all()
          and (m["defaults_sql"] == m["defaults_py"]).all())
    return [_check("sql", "SQL segment counts match independent Python (pandas) segmentation", ok,
                   f"{len(m)} segment rows compared")]
