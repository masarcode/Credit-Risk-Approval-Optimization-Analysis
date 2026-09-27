import numpy as np
import pandas as pd

from credit_risk.clean import clean_applications
from credit_risk.generate_data import generate, simulate_applicants

PROTECTED_OR_PROXY_TERMS = ["race", "ethnic", "religion", "sex", "gender", "orientation", "disab",
                            "marital", "national", "origin", "age", "birth", "zip", "postal", "address",
                            "citizen", "language", "name"]


def test_generation_is_deterministic(config):
    a = generate(config)
    b = generate(config)
    pd.testing.assert_frame_equal(a, b)


def test_different_seed_gives_different_data():
    a = simulate_applicants(1_000, seed=1)
    b = simulate_applicants(1_000, seed=2)
    assert not a["credit_score"].equals(b["credit_score"])


def test_raw_file_contains_injected_issues(config):
    raw = generate(config)
    issues = config["raw_data_issues"]
    n = config["project"]["n_applicants"]
    assert len(raw) == n + issues["duplicate_rows"]
    assert raw.duplicated().sum() == issues["duplicate_rows"]
    assert raw["employment_length"].isna().sum() > 0
    assert raw["revolving_utilization"].isna().sum() > 0
    assert (raw["debt_to_income_ratio"] > 1).sum() > 0


def test_no_protected_characteristics_or_obvious_proxies(run):
    cols = [c.lower() for c in run["scored"].columns]
    # "applicant_id" and "sample" are allowed; check every other column name
    for col in cols:
        if col in ("applicant_id", "sample"):
            continue
        for term in PROTECTED_OR_PROXY_TERMS:
            assert term not in col, f"column '{col}' looks like a protected field or proxy ('{term}')"


def test_designed_risk_relationships_hold(run):
    df = run["scored"]
    low = df[df["credit_score"] < 620]["observed_default"].mean()
    high = df[df["credit_score"] >= 700]["observed_default"].mean()
    assert low > 3 * high
    assert df[df["debt_to_income_ratio"] >= 0.4]["observed_default"].mean() > \
        df[df["debt_to_income_ratio"] < 0.1]["observed_default"].mean()
    assert df[df["recent_delinquencies"] >= 2]["observed_default"].mean() > \
        df[df["recent_delinquencies"] == 0]["observed_default"].mean()


def test_relationships_are_not_deterministic(run):
    """Randomness: some high-score applicants default and some low-score applicants repay."""
    df = run["scored"]
    assert df[df["credit_score"] >= 740]["observed_default"].sum() > 0
    assert (df[df["credit_score"] < 580]["observed_default"] == 0).sum() > 0


def test_clean_data_has_expected_shape(run, config):
    df = run["scored"]
    assert len(df) == config["project"]["n_applicants"]
    assert df["applicant_id"].is_unique
    assert not df.isna().any().any()
    assert np.isclose(df["loan_to_income_ratio"], (df["requested_loan_amount"] / df["annual_income"]).round(4)).all()


def test_cleaning_log_counts_match_raw_issues(config):
    raw = generate(config)
    clean, log = clean_applications(raw)
    assert log["exact_duplicates_removed"] == config["raw_data_issues"]["duplicate_rows"]
    assert log["dti_percent_values_rescaled"] == int((raw.drop_duplicates()["debt_to_income_ratio"] > 1).sum())
    assert clean["employment_length_imputed_flag"].sum() == log["employment_length_imputed"]
    assert clean["revolving_utilization_imputed_flag"].sum() == log["revolving_utilization_imputed"]
    assert clean["debt_to_income_ratio"].max() <= 0.60
