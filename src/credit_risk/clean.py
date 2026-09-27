"""Clean the raw application file and add derived analysis fields.

Every change is counted in a cleaning log so the number of records touched
by each rule is reported, not hidden.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def clean_applications(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = raw.copy()
    log: dict[str, int | float] = {"raw_rows": len(df)}

    # 1. Exact duplicate submissions. A duplicated applicant_id with
    #    different field values would be a conflict, not a duplicate, so we
    #    check for that explicitly before dropping.
    exact_dupes = df.duplicated(keep="first")
    log["exact_duplicates_removed"] = int(exact_dupes.sum())
    df = df.loc[~exact_dupes].copy()
    conflicting = df["applicant_id"].duplicated(keep=False)
    if conflicting.any():
        raise ValueError(f"{int(conflicting.sum())} applicant_ids have conflicting records")

    # 2. DTI unit inconsistency: DTI is a ratio capped at 0.60, so any value
    #    above 1.0 can only be a percentage that was keyed as a whole number.
    pct_mask = df["debt_to_income_ratio"] > 1.0
    log["dti_percent_values_rescaled"] = int(pct_mask.sum())
    df.loc[pct_mask, "debt_to_income_ratio"] = (df.loc[pct_mask, "debt_to_income_ratio"] / 100).round(4)

    # 3. Missing values: impute with the median and keep a flag so the
    #    imputation is visible to anyone using the data.
    for col in ["employment_length", "revolving_utilization"]:
        missing = df[col].isna()
        median = float(df[col].median())
        log[f"{col}_imputed"] = int(missing.sum())
        log[f"{col}_median_used"] = median
        df[f"{col}_imputed_flag"] = missing.astype(int)
        df.loc[missing, col] = median

    # 4. Derived fields used by the score and the segmentation
    df["loan_to_income_ratio"] = (df["requested_loan_amount"] / df["annual_income"]).round(4)
    df["log_annual_income"] = np.log(df["annual_income"])
    df["employment_length_capped"] = df["employment_length"].clip(upper=10)

    # Stable ordering by applicant id makes downstream outputs reproducible
    df = df.sort_values("applicant_id").reset_index(drop=True)
    for col in ["credit_score", "number_of_open_accounts", "recent_delinquencies",
                "recent_credit_inquiries", "previous_default_flag", "observed_default"]:
        df[col] = df[col].astype(int)

    log["clean_rows"] = len(df)
    return df, log
