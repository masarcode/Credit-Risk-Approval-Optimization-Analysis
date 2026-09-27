import pandas as pd
import pytest

from credit_risk.scenarios import break_even_default_rate, recommend, thresholds


def test_twelve_scenarios_in_five_point_steps(run, config):
    s = run["scenarios"]
    assert len(s) == 12
    assert s["threshold"].tolist() == thresholds(config)
    assert s["threshold"].diff().dropna().eq(config["scenarios"]["step"]).all()
    assert s.iloc[0]["is_baseline"] and s["is_baseline"].sum() == 1


def test_tradeoff_directions(run):
    s = run["scenarios"]
    assert s["approval_rate"].is_monotonic_decreasing
    assert s["approved_defaults"].is_monotonic_decreasing
    assert s["default_rate"].is_monotonic_decreasing
    assert (s["pct_change_defaults"].iloc[1:] < s["pct_change_approvals"].iloc[1:]).all(), \
        "defaults should fall proportionally faster than approvals"


def test_diminishing_returns(run):
    """Each extra step removes fewer defaults per approval lost (allowing small noise)."""
    s = run["scenarios"]
    assert s["marginal_default_rate"].iloc[1] > s["marginal_default_rate"].iloc[-1]
    assert s["defaults_avoided_per_100_approvals_lost"].dropna().is_monotonic_decreasing


def test_metrics_reconcile(run):
    s, df = run["scenarios"], run["scored"]
    assert (s["approved"] + s["declined"] == len(df)).all()
    assert s["approval_rate"].equals(s["approved"] / len(df))
    assert (s["marginal_declined"].iloc[1:] == -s["approved"].diff().iloc[1:]).all()
    assert s["expected_defaults"].sub(s["approved_defaults"]).abs().div(s["approved_defaults"]).max() < 0.06


def test_break_even_formula():
    assert break_even_default_rate(0.12, 0.75) == pytest.approx(0.12 / 0.87)


def test_recommend_rule_on_toy_data():
    toy = pd.DataFrame({"threshold": [500, 505, 510, 515, 520],
                        "marginal_default_rate": [None, 0.30, 0.20, 0.10, 0.25]})
    # stops at the first slice below break-even even if a later slice is higher
    assert recommend(toy, 0.15)["threshold"] == 510
    assert recommend(toy, 0.35)["threshold"] == 500
    assert recommend(toy, 0.05)["threshold"] == 520 and recommend(toy, 0.05)["at_grid_edge"]


def test_recommendation_is_consistent_with_rule(run):
    s, h = run["scenarios"], run["headline"]
    rec = s[s["threshold"] == h["recommended_threshold"]].index[0]
    be = h["break_even_default_rate"]
    assert (s.loc[1:rec, "marginal_default_rate"] >= be).all()
    if rec + 1 < len(s):
        assert s.loc[rec + 1, "marginal_default_rate"] < be
    # The dollar view agrees: contribution peaks at the recommended cutoff
    assert h["max_net_contribution_threshold"] == h["recommended_threshold"]


def test_risk_appetite_ordering(run):
    sens = run["sensitivity"].set_index("risk_appetite")
    assert sens.loc["conservative", "recommended_threshold"] >= sens.loc["base", "recommended_threshold"] \
        >= sens.loc["growth", "recommended_threshold"]
    assert sens.loc["base", "recommended_threshold"] == run["headline"]["recommended_threshold"]


def test_result_holds_on_holdout_sample(run):
    h = run["headline"]
    ho = h["holdout_check"]
    assert abs(ho["holdout_pct_change_defaults"] - h["pct_change_defaults"]) < 0.03
    assert abs(ho["holdout_pct_change_approvals"] - h["pct_change_approvals"]) < 0.02
