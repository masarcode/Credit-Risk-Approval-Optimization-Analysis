"""Single source of truth for field definitions (used by Excel, docs and tests)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

# (field, plain-English meaning, type, units / valid range, role in analysis)
FIELDS = [
    ("applicant_id", "Unique identifier for one loan application", "Text", "APP-000001 to APP-100000", "Key"),
    ("annual_income", "Applicant's stated gross annual income", "Number", "$12,000 to $500,000", "Score input (as log income); segmentation"),
    ("employment_length", "Years with current employer (median-imputed when missing)", "Number", "0 to 40 years", "Score input (capped at 10 years)"),
    ("credit_score", "Synthetic credit-bureau-style score. Not a FICO score", "Integer", "300 to 850", "Score input; segmentation"),
    ("credit_history_length", "Years since the applicant's oldest credit account was opened", "Number", "0.5 to 45 years", "Tested for the score, not retained; descriptive"),
    ("number_of_open_accounts", "Count of currently open credit accounts", "Integer", "0 or more", "Tested for the score, not retained; descriptive"),
    ("revolving_utilization", "Credit card balances divided by credit card limits (median-imputed when missing)", "Ratio", "0 to 1 (0% to 100%)", "Score input; segmentation"),
    ("recent_delinquencies", "Payments 30+ days late in the last 24 months", "Integer", "0 or more", "Score input; segmentation"),
    ("recent_credit_inquiries", "Hard credit inquiries in the last 6 months", "Integer", "0 or more", "Score input"),
    ("previous_default_flag", "1 if the credit file shows a prior charge-off or default before this application", "Binary", "0 or 1", "Score input"),
    ("debt_to_income_ratio", "Existing monthly debt payments divided by gross monthly income (before the new loan)", "Ratio", "0 to 0.60 (0% to 60%)", "Score input; segmentation"),
    ("existing_debt", "Total outstanding non-mortgage debt balance", "Number", "$0 or more", "Descriptive"),
    ("requested_loan_amount", "Unsecured personal loan amount requested", "Number", "$1,000 to $50,000", "Score input (via loan-to-income); loss dollars; segmentation"),
    ("loan_to_income_ratio", "Requested loan amount divided by annual income (derived)", "Ratio", "0 or more", "Score input"),
    ("log_annual_income", "Natural log of annual income (derived; used so a 10% raise has the same effect at any income level)", "Number", "About 9.4 to 13.1", "Score input"),
    ("employment_length_capped", "Employment length capped at 10 years (derived; tenure beyond 10 years adds no extra credit)", "Number", "0 to 10 years", "Score input"),
    ("employment_length_imputed_flag", "1 if employment length was missing in the raw file and filled with the median", "Binary", "0 or 1", "Data quality flag"),
    ("revolving_utilization_imputed_flag", "1 if utilization was missing in the raw file and filled with the median", "Binary", "0 or 1", "Data quality flag"),
    ("observed_default", "1 if the loan defaulted during its term in the simulation (the outcome)", "Binary", "0 or 1", "Outcome being predicted"),
    ("sample", "Whether the record was used to build the score (development, 70%) or only to test it (holdout, 30%)", "Text", "development / holdout", "Model validation"),
    ("predicted_pd", "Probability of default estimated by the scoring model", "Probability", "0 to 1", "Expected defaults and expected loss"),
    ("risk_score", "Synthetic Risk Score (SRS). Higher = lower risk. 600 = 20-to-1 odds of repaying; every +20 points doubles the odds", "Integer", "Roughly 330 to 720 in this data", "Approval decision: approve if score >= cutoff"),
]

EXCLUDED_BY_DESIGN = (
    "No race, ethnicity, religion, sex, sexual orientation, disability, marital status, national origin, "
    "age, or geographic fields (such as ZIP code) are generated or used."
)


def as_frame() -> pd.DataFrame:
    return pd.DataFrame(FIELDS, columns=["Field", "Meaning", "Type", "Units / valid range", "Role in analysis"])


def as_markdown() -> str:
    df = as_frame()
    lines = ["| " + " | ".join(df.columns) + " |", "|" + "---|" * len(df.columns)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(f"`{row[0]}`" if i == 0 else str(v) for i, v in enumerate(row)) + " |")
    return "\n".join(lines)


SEGMENT_NAMES = {
    "credit_score_band": "Credit score", "income_band": "Income", "dti_band": "Debt-to-income",
    "utilization_band": "Card utilization", "delinquency_band": "Recent delinquencies", "loan_size_band": "Loan size",
}

OUTPUT_TABLES = [
    ("outputs/tables/scenario_results.csv", "One row per cutoff (12)", "Every scenario metric, changes vs baseline, marginal slice metrics"),
    ("outputs/tables/risk_appetite_sensitivity.csv", "One row per risk appetite (3)", "Recommended cutoff under different margin assumptions"),
    ("outputs/tables/sql_segment_default_rates.csv", "Dimension x band", "Default rate, share of defaults, approval rates at baseline and recommended cutoffs"),
    ("outputs/tables/sql_risk_concentration_matrix.csv", "Credit score band x DTI band", "Defaults and cumulative share of defaults"),
    ("outputs/tables/sql_highest_risk_profiles.csv", "Top 10 profiles", "Score x DTI x utilization combinations with the highest default rates (300+ applicants)"),
    ("outputs/tables/sql_tightening_impact.csv", "Dimension x band", "Approvals lost and defaults avoided when moving to the recommended cutoff"),
    ("outputs/tables/sql_scenario_summary.csv", "One row per cutoff", "Independent SQL version of the scenarios (reconciled to Python)"),
    ("outputs/tables/sql_score_band_distribution.csv", "10-point score band", "Applicants, defaults and average predicted PD"),
    ("outputs/tables/score_drivers.csv", "One row per score factor", "Coefficient, p-value, odds multiplier and score-point impact"),
    ("outputs/tables/model_feature_screening.csv", "One row per candidate feature", "Why each feature was kept or dropped"),
    ("outputs/tables/holdout_calibration.csv", "Risk decile", "Predicted vs observed default rate on the holdout"),
    ("outputs/tables/validation_report.csv", "One row per check", "Pipeline validation results"),
    ("outputs/tables/cleaning_log.csv", "One row per cleaning rule", "Records affected by each cleaning step"),
    ("outputs/tables/headline_metrics.json", "Single record", "Headline numbers used in the README and executive summary"),
]


def write_markdown(path: Path, config: dict) -> Path:
    """Write docs/data_dictionary.md from the same definitions the workbook uses."""
    bands = [f"| {SEGMENT_NAMES[k]} | `{k}` | {', '.join(v['labels'])} |" for k, v in config["segments"].items()]
    tables = [f"| `{f}` | {g} | {d} |" for f, g, d in OUTPUT_TABLES]
    lines = [
        "# Data Dictionary", "",
        "Applicant-level fields in `data/processed/applications_scored.csv` and the SQLite table `applicants`. "
        "All values are synthetic.", "",
        f"**Excluded by design.** {EXCLUDED_BY_DESIGN}", "",
        "## Fields", "", as_markdown(), "",
        "## Segment bands", "",
        "Defined in the SQL view `applicant_segments` (`sql/create_tables.sql`) and mirrored in "
        "`config/analysis_config.yaml`; a test checks the two agree. Bands include the lower bound and exclude the "
        "upper bound (for example, `620-659` means 620 <= score < 660).", "",
        "| Dimension | Column in `applicant_segments` | Bands |", "|---|---|---|", *bands, "",
        "## Output tables", "",
        "| File | Grain | Description |", "|---|---|---|", *tables, "",
        "*This file is generated by the pipeline from `src/credit_risk/data_dictionary.py`.*", "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
