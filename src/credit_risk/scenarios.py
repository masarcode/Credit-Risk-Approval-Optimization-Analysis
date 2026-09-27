"""Threshold scenarios and the decision framework.

An applicant is approved when ``risk_score >= threshold``. The baseline is
the assumed current cutoff; each further scenario raises the cutoff by a
fixed number of points.

Decision rule (marginal break-even)
-----------------------------------
Raising the cutoff from one scenario to the next declines one "slice" of
applicants: those scoring between the two cutoffs. Declining that slice is
worth it only if those applicants would, on average, cost the lender more
in losses than they earn in interest.

With a lifetime net margin ``m`` on loans that repay and a loss given
default ``LGD`` on loans that do not, a slice breaks even when its default
rate equals::

    break_even_default_rate = m / (m + LGD)

So we keep tightening while the slice being removed defaults at or above
the break-even rate, and stop at the first slice that defaults below it
(declining those applicants would give up more good business than it saves
in losses). The cutoff reached this way is the recommendation.

Every number here is computed from applicant-level data; nothing is
hard-coded.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def thresholds(config: dict) -> list[int]:
    sc = config["scenarios"]
    return [sc["baseline_threshold"] + i * sc["step"] for i in range(sc["count"])]


def break_even_default_rate(margin: float, lgd: float) -> float:
    return margin / (margin + lgd)


def compute_scenarios(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    econ = config["economics"]
    lgd, margin = econ["loss_given_default"], econ["net_margin_on_good_loans"]
    base_t = config["scenarios"]["baseline_threshold"]
    n = len(df)

    rows = []
    for i, t in enumerate(thresholds(config)):
        a = df[df["risk_score"] >= t]
        loans = a["requested_loan_amount"]
        d = a["observed_default"]
        rows.append({
            "scenario_id": f"S{i + 1:02d}",
            "scenario_label": "Baseline" if t == base_t else f"Baseline +{t - base_t}",
            "threshold": t,
            "points_above_baseline": t - base_t,
            "is_baseline": t == base_t,
            "approved": len(a),
            "declined": n - len(a),
            "approval_rate": len(a) / n,
            "approved_defaults": int(d.sum()),
            "default_rate": float(d.mean()),
            "expected_defaults": float(a["predicted_pd"].sum()),
            "approved_loan_volume": float(loans.sum()),
            "defaulted_loan_volume": float((loans * d).sum()),
            "estimated_credit_loss": float((loans * d).sum() * lgd),
            "expected_loss": float((loans * a["predicted_pd"]).sum() * lgd),
            "est_net_contribution": float((loans * ((1 - d) * margin - d * lgd)).sum()),
            "avg_credit_score": float(a["credit_score"].mean()),
            "avg_risk_score": float(a["risk_score"].mean()),
            "avg_annual_income": float(a["annual_income"].mean()),
            "avg_dti": float(a["debt_to_income_ratio"].mean()),
            "avg_utilization": float(a["revolving_utilization"].mean()),
            "avg_loan_amount": float(loans.mean()),
        })
    s = pd.DataFrame(rows)

    b = s.iloc[0]
    s["loss_rate"] = s["estimated_credit_loss"] / s["approved_loan_volume"]
    s["expected_loss_per_approved"] = s["expected_loss"] / s["approved"]
    s["approvals_change"] = s["approved"] - b["approved"]
    s["pct_change_approvals"] = s["approvals_change"] / b["approved"]
    s["defaults_change"] = s["approved_defaults"] - b["approved_defaults"]
    s["pct_change_defaults"] = s["defaults_change"] / b["approved_defaults"]
    s["pct_change_credit_loss"] = s["estimated_credit_loss"] / b["estimated_credit_loss"] - 1
    s["pct_change_net_contribution"] = s["est_net_contribution"] / b["est_net_contribution"] - 1

    # Cumulative efficiency: how many defaults are avoided per 100 approvals given up
    lost = -s["approvals_change"]
    avoided = -s["defaults_change"]
    s["defaults_avoided_per_100_approvals_lost"] = np.where(lost > 0, 100 * avoided / lost.replace(0, np.nan), np.nan)
    s["risk_reduction_ratio"] = np.where(
        s["pct_change_approvals"] < 0, s["pct_change_defaults"] / s["pct_change_approvals"].replace(0, np.nan), np.nan)

    # Marginal slice: applicants removed by moving from the previous cutoff to this one
    s["marginal_declined"] = -s["approved"].diff()
    s["marginal_defaults_avoided"] = -s["approved_defaults"].diff()
    s["marginal_good_loans_lost"] = s["marginal_declined"] - s["marginal_defaults_avoided"]
    s["marginal_default_rate"] = s["marginal_defaults_avoided"] / s["marginal_declined"]
    exp_prev = s["expected_defaults"].shift(1)
    s["marginal_predicted_pd"] = (exp_prev - s["expected_defaults"]) / s["marginal_declined"]
    s["break_even_default_rate"] = break_even_default_rate(margin, lgd)
    s["marginal_slice_above_break_even"] = s["marginal_default_rate"] >= s["break_even_default_rate"]
    return s


def recommend(s: pd.DataFrame, break_even: float) -> dict:
    """Tighten step by step while the removed slice defaults at or above break-even."""
    idx = 0
    for k in range(1, len(s)):
        if s.iloc[k]["marginal_default_rate"] >= break_even:
            idx = k
        else:
            break
    at_edge = idx == len(s) - 1
    return {"index": idx, "threshold": int(s.iloc[idx]["threshold"]), "at_grid_edge": at_edge}


def risk_appetite_sensitivity(s: pd.DataFrame, config: dict) -> pd.DataFrame:
    econ = config["economics"]
    rows = []
    for name, m in econ["sensitivity_margins"].items():
        be = break_even_default_rate(m, econ["loss_given_default"])
        r = recommend(s, be)
        row = s.iloc[r["index"]]
        rows.append({
            "risk_appetite": name,
            "assumed_net_margin": m,
            "loss_given_default": econ["loss_given_default"],
            "break_even_default_rate": be,
            "recommended_threshold": r["threshold"],
            "approval_rate": row["approval_rate"],
            "pct_change_approvals": row["pct_change_approvals"],
            "pct_change_defaults": row["pct_change_defaults"],
            "default_rate": row["default_rate"],
            "at_grid_edge": r["at_grid_edge"],
        })
    return pd.DataFrame(rows)


def holdout_check(df: pd.DataFrame, base_t: int, rec_t: int) -> dict:
    """Re-measure the recommended change on the 30% holdout the score never saw."""
    h = df[df["sample"] == "holdout"]
    b, r = h[h["risk_score"] >= base_t], h[h["risk_score"] >= rec_t]
    return {
        "holdout_applicants": int(len(h)),
        "holdout_pct_change_approvals": len(r) / len(b) - 1,
        "holdout_pct_change_defaults": r["observed_default"].sum() / b["observed_default"].sum() - 1,
        "holdout_baseline_default_rate": float(b["observed_default"].mean()),
        "holdout_recommended_default_rate": float(r["observed_default"].mean()),
    }
