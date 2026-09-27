"""The validators must pass on real output AND catch deliberately broken data."""
import pandas as pd
import pytest

from credit_risk import validate as v
from credit_risk.clean import clean_applications


def _failed(checks):
    return [c.check for c in checks if not c.passed]


def test_every_pipeline_check_passed(run):
    val = run["validation"]
    assert len(val) >= 30
    assert val["passed"].all(), val.loc[~val["passed"], "check"].tolist()


def test_validation_report_written(run, config):
    path = run["root"] / config["paths"]["tables_dir"] / "validation_report.csv"
    saved = pd.read_csv(path)
    assert len(saved) == len(run["validation"])


@pytest.mark.parametrize("column,bad_value,expected_fragment", [
    ("credit_score", 900, "credit_score within"),
    ("credit_score", 250, "credit_score within"),
    ("debt_to_income_ratio", 0.95, "debt_to_income_ratio within"),
    ("revolving_utilization", 1.4, "revolving_utilization within"),
    ("annual_income", -5_000, "annual_income within"),
    ("requested_loan_amount", -1, "requested_loan_amount within"),
    ("observed_default", 2, "observed_default is binary"),
    ("existing_debt", -10, "non-negative"),
])
def test_validator_catches_impossible_values(run, config, column, bad_value, expected_fragment):
    df = run["scored"].copy()
    df.loc[df.index[0], column] = bad_value
    failed = _failed(v.validate_clean(df, config))
    assert any(expected_fragment in f for f in failed), failed


def test_validator_catches_duplicate_ids_and_missing_rows(run, config):
    df = run["scored"].copy()
    df.loc[df.index[1], "applicant_id"] = df.loc[df.index[0], "applicant_id"]
    assert "applicant_id is unique" in _failed(v.validate_clean(df, config))
    short = run["scored"].iloc[:-1]
    assert any("records" in f for f in _failed(v.validate_clean(short, config)))


def test_validator_catches_missing_values(run, config):
    df = run["scored"].copy()
    df.loc[df.index[0], "annual_income"] = None
    assert "no missing values in any column" in _failed(v.validate_clean(df, config))


def test_validator_catches_non_monotonic_scenarios(run, config):
    scen = run["scenarios"].copy()
    scen.loc[5, "approval_rate"] = scen.loc[4, "approval_rate"] + 0.01
    assert "approval rate falls as the threshold tightens" in _failed(v.validate_scenarios(scen, run["scored"], config))


def test_validator_catches_scenarios_that_do_not_reconcile(run, config):
    scen = run["scenarios"].copy()
    scen.loc[3, "approved_defaults"] += 1
    failed = _failed(v.validate_scenarios(scen, run["scored"], config))
    assert "every scenario reconciles to the applicant-level data" in failed


def test_cleaning_rejects_conflicting_duplicate_ids():
    raw = pd.DataFrame({
        "applicant_id": ["APP-000001", "APP-000001"],
        "employment_length": [1.0, 2.0], "revolving_utilization": [0.1, 0.1],
        "debt_to_income_ratio": [0.2, 0.2], "requested_loan_amount": [5000, 5000],
        "annual_income": [50000, 50000],
    })
    with pytest.raises(ValueError, match="conflicting"):
        clean_applications(raw)
