"""Generate the synthetic consumer credit application dataset.

Design
------
Each applicant gets two hidden (latent) traits drawn from a standard normal
distribution:

* ``quality``   - underlying credit quality (payment discipline)
* ``stability`` - financial / career stability

Observable fields are built from these traits plus independent noise, so
the fields are correlated with each other the way real bureau and
application data are, without any single field fully determining risk.

The true probability of default is then computed from the observable fields
plus an unobserved random component. That unobserved component is why no
score built from the data can predict default perfectly, which mirrors
reality.

No protected characteristics (race, sex, age, marital status, national
origin, etc.) and no geographic fields are generated.

Finally, a small number of realistic data-quality problems are injected
into the raw file (duplicates, missing values, a unit inconsistency) so the
cleaning step has genuine work to do.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# True default model used ONLY to simulate outcomes. The scoring step never
# sees these coefficients; it has to estimate risk from the data.
# Coefficients are on the log-odds of default.
# ---------------------------------------------------------------------------
TRUE_DEFAULT_MODEL = {
    "intercept": -3.00,
    "credit_score_per_point": -0.010,   # centred at 680
    "dti": 2.5,                         # centred at 0.21
    "utilization": 1.0,                 # centred at 0.35
    "delinquency_each": 0.30,
    "previous_default": 0.70,
    "inquiry_each": 0.10,
    "loan_to_income": 2.0,              # centred at 0.20
    "log_income": -0.30,                # log(income / 58,000)
    "employment_year_capped_10": -0.03,
    "latent_quality": -0.25,            # part of credit quality the data never shows
    "unobserved_noise_sd": 0.60,
}


def _logistic(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def simulate_applicants(n: int, seed: int) -> pd.DataFrame:
    """Simulate ``n`` clean applicant records (before quality issues)."""
    rng = np.random.default_rng(seed)

    quality = rng.standard_normal(n)
    stability = 0.3 * quality + np.sqrt(1 - 0.3**2) * rng.standard_normal(n)

    # --- Credit profile -----------------------------------------------------
    credit_score = np.clip(np.round(680 + 65 * quality + rng.normal(0, 25, n)), 300, 850).astype(int)

    revolving_utilization = np.round(_logistic(-0.7 - 0.9 * quality + rng.normal(0, 0.8, n)), 3)

    recent_delinquencies = rng.poisson(np.exp(-1.8 - 0.9 * quality))
    previous_default_flag = rng.binomial(1, _logistic(-3.2 - 1.1 * quality))
    recent_credit_inquiries = rng.poisson(np.exp(0.1 - 0.35 * quality))

    history_driver = 0.8 * stability + 0.2 * quality
    credit_history_length = np.clip(np.round(10 + 5 * history_driver + rng.normal(0, 3, n), 1), 0.5, 45.0)
    number_of_open_accounts = rng.poisson(np.exp(1.9 + 0.25 * history_driver))

    # --- Income, employment and debt ---------------------------------------
    employment_length = np.clip(np.round(np.exp(1.5 + 0.5 * stability + rng.normal(0, 0.6, n)) - 1, 1), 0.0, 40.0) + 0.0

    annual_income = np.exp(np.log(58_000) + 0.25 * stability + 0.15 * quality + rng.normal(0, 0.45, n))
    annual_income = np.clip(np.round(annual_income, -2), 12_000, 500_000)

    # DTI = existing monthly debt payments / gross monthly income, capped at 60%
    debt_to_income_ratio = np.round(0.60 * _logistic(-0.6 - 0.4 * quality + rng.normal(0, 0.6, n)), 4)

    # Existing debt balance implied by the monthly payments (balance is
    # roughly 18-36x the monthly payment for a mix of auto/student/card debt)
    balance_multiple = rng.uniform(18, 36, n)
    existing_debt = np.round(debt_to_income_ratio * annual_income / 12 * balance_multiple, -1)

    # Requested unsecured personal loan, scaling loosely with income
    requested_loan_amount = np.exp(np.log(12_000) + 0.35 * np.log(annual_income / 58_000) + rng.normal(0, 0.5, n))
    requested_loan_amount = np.clip(np.round(requested_loan_amount / 250) * 250, 1_000, 50_000)

    # --- Outcome -----------------------------------------------------------
    m = TRUE_DEFAULT_MODEL
    loan_to_income = requested_loan_amount / annual_income
    log_odds = (
        m["intercept"]
        + m["credit_score_per_point"] * (credit_score - 680)
        + m["dti"] * (debt_to_income_ratio - 0.21)
        + m["utilization"] * (revolving_utilization - 0.35)
        + m["delinquency_each"] * recent_delinquencies
        + m["previous_default"] * previous_default_flag
        + m["inquiry_each"] * recent_credit_inquiries
        + m["loan_to_income"] * (loan_to_income - 0.20)
        + m["log_income"] * np.log(annual_income / 58_000)
        + m["employment_year_capped_10"] * np.minimum(employment_length, 10)
        + m["latent_quality"] * quality
        + rng.normal(0, m["unobserved_noise_sd"], n)
    )
    true_pd = _logistic(log_odds)
    observed_default = rng.binomial(1, true_pd)

    return pd.DataFrame(
        {
            "applicant_id": [f"APP-{i:06d}" for i in range(1, n + 1)],
            "annual_income": annual_income,
            "employment_length": employment_length,
            "credit_score": credit_score,
            "credit_history_length": credit_history_length,
            "number_of_open_accounts": number_of_open_accounts,
            "revolving_utilization": revolving_utilization,
            "recent_delinquencies": recent_delinquencies,
            "recent_credit_inquiries": recent_credit_inquiries,
            "previous_default_flag": previous_default_flag,
            "debt_to_income_ratio": debt_to_income_ratio,
            "existing_debt": existing_debt,
            "requested_loan_amount": requested_loan_amount,
            "observed_default": observed_default,
        }
    )


def inject_quality_issues(df: pd.DataFrame, issues: dict, seed: int) -> pd.DataFrame:
    """Add realistic raw-data problems that the cleaning step must fix."""
    rng = np.random.default_rng(seed + 1)
    raw = df.copy()
    n = len(raw)

    miss_emp = rng.random(n) < issues["missing_employment_length_rate"]
    raw.loc[miss_emp, "employment_length"] = np.nan

    miss_util = rng.random(n) < issues["missing_utilization_rate"]
    raw.loc[miss_util, "revolving_utilization"] = np.nan

    pct = rng.random(n) < issues["dti_recorded_as_percent_rate"]
    raw.loc[pct, "debt_to_income_ratio"] = (raw.loc[pct, "debt_to_income_ratio"] * 100).round(2)

    dup_idx = rng.choice(n, size=issues["duplicate_rows"], replace=False)
    raw = pd.concat([raw, raw.iloc[dup_idx]], ignore_index=True)

    # Shuffle so duplicates are not conveniently at the bottom
    raw = raw.sample(frac=1.0, random_state=seed % (2**32)).reset_index(drop=True)
    return raw


def generate(config: dict) -> pd.DataFrame:
    seed = config["project"]["random_seed"]
    clean = simulate_applicants(config["project"]["n_applicants"], seed)
    return inject_quality_issues(clean, config["raw_data_issues"], seed)
