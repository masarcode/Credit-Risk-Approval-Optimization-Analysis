"""Build the Synthetic Risk Score (SRS).

Method
------
1. Split applicants 70/30 into a development sample and a holdout sample.
2. Fit a logistic regression of ``observed_default`` on a short list of
   candidate features using the development sample only.
3. Keep a feature only if it is statistically clear (p < 0.01) AND its
   direction matches basic credit logic. Refit on the kept features.
4. Convert the predicted probability of default (PD) into points using the
   standard scorecard convention: 600 points = 20:1 odds of repaying, and
   every 20 points doubles those odds. Higher score = lower risk.
5. Check rank-ordering (AUC, KS) and calibration on the holdout sample,
   which the model never saw.

Logistic regression is used because every coefficient can be read directly
("each extra delinquency multiplies the odds of default by X"). Nothing
more complex is needed for a threshold analysis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

# Plain-English description of a meaningful change in each feature, used to
# express the model as score points ("what moves the score").
DRIVER_EXAMPLES = {
    "credit_score": (50, "+50 credit score points"),
    "debt_to_income_ratio": (0.10, "+10 points of DTI (e.g. 20% to 30%)"),
    "revolving_utilization": (0.20, "+20 points of card utilization"),
    "recent_delinquencies": (1, "+1 recent delinquency"),
    "previous_default_flag": (1, "has a prior default"),
    "recent_credit_inquiries": (1, "+1 recent credit inquiry"),
    "loan_to_income_ratio": (0.10, "loan +10% of annual income"),
    "log_annual_income": (np.log(1.5), "income 50% higher"),
    "employment_length_capped": (5, "+5 years employment (capped at 10)"),
    "credit_history_length": (5, "+5 years credit history"),
    "number_of_open_accounts": (3, "+3 open accounts"),
}


def auc(y: np.ndarray, p: np.ndarray) -> float:
    """Area under the ROC curve via the rank (Mann-Whitney) formula."""
    y = np.asarray(y)
    ranks = pd.Series(p).rank(method="average").to_numpy()
    n1 = y.sum()
    n0 = len(y) - n1
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def ks_statistic(y: np.ndarray, p: np.ndarray) -> float:
    """Max distance between cumulative distributions of defaulters and non-defaulters."""
    d = pd.DataFrame({"y": y, "p": p}).sort_values("p", ascending=False)
    cum_bad = d["y"].cumsum() / d["y"].sum()
    cum_good = (1 - d["y"]).cumsum() / (1 - d["y"]).sum()
    return float((cum_bad - cum_good).max())


def split_sample(df: pd.DataFrame, share: float, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed + 2)
    is_dev = rng.random(len(df)) < share
    return pd.Series(np.where(is_dev, "development", "holdout"), index=df.index)


def _fit(df: pd.DataFrame, features: list[str]):
    X = sm.add_constant(df[features], has_constant="add")
    return sm.Logit(df["observed_default"], X).fit(disp=False)


def pd_to_score(pd_: np.ndarray, base_score: float, base_odds: float, pdo: float) -> np.ndarray:
    factor = pdo / np.log(2)
    odds_good = (1 - pd_) / pd_
    return base_score + factor * (np.log(odds_good) - np.log(base_odds))


def score_to_pd(score: np.ndarray, base_score: float, base_odds: float, pdo: float) -> np.ndarray:
    factor = pdo / np.log(2)
    odds_good = base_odds * np.exp((np.asarray(score) - base_score) / factor)
    return 1 / (1 + odds_good)


def build_score(df: pd.DataFrame, config: dict):
    """Return (scored data, summary dict, feature screening, score drivers, holdout calibration)."""
    sc = config["scoring"]
    seed = config["project"]["random_seed"]
    out = df.copy()
    out["sample"] = split_sample(out, sc["development_share"], seed)
    dev = out[out["sample"] == "development"]
    hold = out[out["sample"] == "holdout"]

    # Step 1: full candidate model and feature screening
    full = _fit(dev, sc["candidate_features"])
    screening = []
    for f in sc["candidate_features"]:
        coef, pval = float(full.params[f]), float(full.pvalues[f])
        sign_ok = np.sign(coef) == sc["expected_signs"][f]
        keep = bool(pval < sc["retention_p_value"] and sign_ok)
        reason = "kept" if keep else ("wrong direction" if not sign_ok else "not statistically clear")
        screening.append({"feature": f, "coefficient": coef, "p_value": pval,
                          "expected_sign": sc["expected_signs"][f], "retained": keep, "reason": reason})
    screening = pd.DataFrame(screening)
    features = screening.loc[screening["retained"], "feature"].tolist()

    # Step 2: final model on kept features
    model = _fit(dev, features)
    X_all = sm.add_constant(out[features], has_constant="add")
    out["predicted_pd"] = model.predict(X_all)
    out["risk_score"] = np.round(
        pd_to_score(out["predicted_pd"].to_numpy(), sc["base_score"], sc["base_odds"], sc["pdo"])
    ).astype(int)

    # Step 3: interpretation table in score points
    factor = sc["pdo"] / np.log(2)
    drivers = []
    for f in features:
        beta = float(model.params[f])
        delta, label = DRIVER_EXAMPLES[f]
        drivers.append({
            "feature": f,
            "coefficient": beta,
            "std_error": float(model.bse[f]),
            "p_value": float(model.pvalues[f]),
            "example_change": label,
            "odds_of_default_multiplier": float(np.exp(beta * delta)),
            "score_point_impact": float(-beta * delta * factor),
        })
    drivers = pd.DataFrame(drivers)

    # Step 4: holdout validation
    calib = hold.assign(predicted_pd=out.loc[hold.index, "predicted_pd"])
    calib["risk_decile"] = pd.qcut(calib["predicted_pd"].rank(method="first"), 10,
                                   labels=range(1, 11)).astype(int)
    calibration = (calib.groupby("risk_decile")
                   .agg(applicants=("observed_default", "size"),
                        mean_predicted_pd=("predicted_pd", "mean"),
                        observed_default_rate=("observed_default", "mean"))
                   .reset_index())

    summary = {
        "score_name": sc["score_name"],
        "features": features,
        "n_development": int(len(dev)),
        "n_holdout": int(len(hold)),
        "intercept": float(model.params["const"]),
        "auc_development": auc(dev["observed_default"].to_numpy(), out.loc[dev.index, "predicted_pd"].to_numpy()),
        "auc_holdout": auc(hold["observed_default"].to_numpy(), out.loc[hold.index, "predicted_pd"].to_numpy()),
        "ks_holdout": ks_statistic(hold["observed_default"].to_numpy(), out.loc[hold.index, "predicted_pd"].to_numpy()),
        "holdout_mean_pd": float(out.loc[hold.index, "predicted_pd"].mean()),
        "holdout_default_rate": float(hold["observed_default"].mean()),
        "pseudo_r2": float(model.prsquared),
        "score_min": int(out["risk_score"].min()),
        "score_max": int(out["risk_score"].max()),
        "score_median": float(out["risk_score"].median()),
    }
    summary["gini_holdout"] = 2 * summary["auc_holdout"] - 1
    return out, summary, screening, drivers, calibration
