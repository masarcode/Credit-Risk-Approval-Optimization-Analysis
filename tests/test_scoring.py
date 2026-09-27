import numpy as np
import pytest

from credit_risk.scoring import auc, ks_statistic, pd_to_score, score_to_pd


def test_auc_known_cases():
    y = np.array([0, 0, 1, 1])
    assert auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == 0.0
    assert auc(y, np.array([0.5, 0.5, 0.5, 0.5])) == 0.5


def test_ks_perfect_separation():
    assert ks_statistic(np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.8, 0.9])) == pytest.approx(1.0)


def test_score_scaling_convention(config):
    sc = config["scoring"]
    args = (sc["base_score"], sc["base_odds"], sc["pdo"])
    # 600 points = 20:1 odds of repaying = PD of 1/21
    assert score_to_pd(np.array([600]), *args)[0] == pytest.approx(1 / 21)
    # +20 points doubles the odds of repaying
    odds = lambda s: (1 - score_to_pd(np.array([s]), *args)[0]) / score_to_pd(np.array([s]), *args)[0]  # noqa: E731
    assert odds(620) / odds(600) == pytest.approx(2.0)
    # score and PD conversions are inverses
    pds = np.array([0.01, 0.05, 0.2, 0.5])
    assert score_to_pd(pd_to_score(pds, *args), *args) == pytest.approx(pds)


def test_feature_screening_rules(run, config):
    scr = run["screening"]
    kept = scr[scr["retained"]]
    assert (kept["p_value"] < config["scoring"]["retention_p_value"]).all()
    assert (np.sign(kept["coefficient"]) == kept["expected_sign"]).all()
    assert run["headline"]["model"]["features"] == kept["feature"].tolist()


def test_score_is_useful_and_not_overfit(run):
    m = run["headline"]["model"]
    assert m["auc_holdout"] > 0.75
    assert abs(m["auc_development"] - m["auc_holdout"]) < 0.02
    assert abs(m["holdout_mean_pd"] - m["holdout_default_rate"]) < 0.01


def test_holdout_calibration_by_decile(run):
    cal = run["calibration"]
    assert len(cal) == 10
    assert cal["observed_default_rate"].is_monotonic_increasing or \
        (cal["observed_default_rate"].diff().dropna() > -0.005).all()
    assert (abs(cal["mean_predicted_pd"] - cal["observed_default_rate"]) < 0.02).all()


def test_higher_score_means_lower_observed_default(run):
    df = run["scored"]
    bands = df.groupby(df["risk_score"] // 25)["observed_default"].agg(["mean", "size"])
    bands = bands[bands["size"] >= 500]["mean"]
    assert bands.is_monotonic_decreasing


def test_score_uses_no_protected_features(run):
    for f in run["headline"]["model"]["features"]:
        assert f in {"credit_score", "debt_to_income_ratio", "revolving_utilization", "recent_delinquencies",
                     "previous_default_flag", "recent_credit_inquiries", "loan_to_income_ratio",
                     "log_annual_income", "employment_length_capped", "credit_history_length",
                     "number_of_open_accounts"}
