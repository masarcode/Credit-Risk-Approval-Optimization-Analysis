# Methodology

This document explains every analytical choice in the project, in the order the pipeline runs. All numbers quoted here come from `outputs/tables/` after running `python scripts/run_pipeline.py` with the fixed seed in `config/analysis_config.yaml`.

> **Educational simulation.** The data is synthetic. The score is not a FICO score or any real lender's model. Nothing here should be used for real credit decisions.

---

## 1. The business question

> How should a lender adjust its approval threshold to reduce expected default exposure while preserving as much approval volume as possible?

The analysis treats this as a trade-off. Declining more applicants always removes some defaults, but it also turns away borrowers who would have repaid. The goal is to find the point where further tightening stops paying for itself, not the point with the fewest defaults (which is "approve nobody").

---

## 2. Synthetic data generation (`src/credit_risk/generate_data.py`)

### 2.1 Design

Each of the 100,000 applicants gets two hidden traits drawn from a standard normal distribution:

| Hidden trait | Meaning | Used for |
|---|---|---|
| `quality` | Underlying credit discipline | Credit score, utilization, delinquencies, prior default, inquiries, DTI |
| `stability` | Financial and career stability (correlation 0.3 with `quality`) | Income, employment length, credit history, open accounts |

Every observable field is a function of these traits **plus its own independent noise**. That gives the fields realistic correlations with each other without any one field fully determining risk.

### 2.2 Field formulas

`N(0, s)` means normal noise with standard deviation `s`. `logistic(x) = 1 / (1 + e^-x)`.

| Field | Formula (before rounding / clipping) | Clipped to |
|---|---|---|
| `credit_score` | 680 + 65 x quality + N(0, 25) | 300 to 850 |
| `revolving_utilization` | logistic(-0.7 - 0.9 x quality + N(0, 0.8)) | 0 to 1 |
| `recent_delinquencies` | Poisson with mean e^(-1.8 - 0.9 x quality) | 0+ |
| `previous_default_flag` | Bernoulli with probability logistic(-3.2 - 1.1 x quality) | 0 / 1 |
| `recent_credit_inquiries` | Poisson with mean e^(0.1 - 0.35 x quality) | 0+ |
| `credit_history_length` | 10 + 5 x (0.8 x stability + 0.2 x quality) + N(0, 3) | 0.5 to 45 years |
| `number_of_open_accounts` | Poisson with mean e^(1.9 + 0.25 x (0.8 x stability + 0.2 x quality)) | 0+ |
| `employment_length` | e^(1.5 + 0.5 x stability + N(0, 0.6)) - 1 | 0 to 40 years |
| `annual_income` | e^(ln 58,000 + 0.25 x stability + 0.15 x quality + N(0, 0.45)) | $12,000 to $500,000 |
| `debt_to_income_ratio` | 0.60 x logistic(-0.6 - 0.4 x quality + N(0, 0.6)) | 0 to 0.60 |
| `existing_debt` | DTI x monthly income x Uniform(18, 36) | 0+ |
| `requested_loan_amount` | e^(ln 12,000 + 0.35 x ln(income / 58,000) + N(0, 0.5)) | $1,000 to $50,000 |

### 2.3 How defaults are simulated

The true log-odds of default for each applicant is:

```
log-odds = -3.00
           - 0.010 x (credit_score - 680)
           + 2.5   x (DTI - 0.21)
           + 1.0   x (utilization - 0.35)
           + 0.30  x recent_delinquencies
           + 0.70  x previous_default_flag
           + 0.10  x recent_credit_inquiries
           + 2.0   x (loan_to_income - 0.20)
           - 0.30  x ln(income / 58,000)
           - 0.03  x min(employment_length, 10)
           - 0.25  x quality            <- part of credit quality the data never shows
           + N(0, 0.60)                 <- unobserved randomness
```

`observed_default` is then a coin flip with that probability. Two parts of the formula are invisible to the analysis (the leftover `quality` term and the random noise). That is deliberate: it means no model built from the data can predict defaults perfectly, which is true in real lending.

Design targets, checked by the validation step rather than forced:

* Weaker credit scores, higher DTI, higher utilization, delinquencies, a prior default and a heavier loan burden all raise risk.
* Roughly 1 in 8 applicants would default if everyone were approved (actual: 13.3%).
* Loan size on its own is only weakly related to risk. What matters is size **relative to income**.

`credit_history_length` and `number_of_open_accounts` have **no direct effect** in the default formula. They are included because lenders see them and a good process should test them rather than assume they matter (see section 4.2).

### 2.4 Data-quality problems added on purpose

Real application files are messy, so the raw file (`data/raw/applications_raw.csv`) includes:

| Issue | Rate | How cleaning fixes it |
|---|---|---|
| Exact duplicate submissions | 250 rows | Dropped. A duplicate ID with *different* values would raise an error instead. |
| Missing employment length | 1.5% | Median imputation plus a `_imputed_flag` column |
| Missing utilization | 0.8% | Median imputation plus a `_imputed_flag` column |
| DTI keyed as a percent (23.5 instead of 0.235) | 0.4% | Values above 1.0 divided by 100 (DTI is capped at 0.60, so this is unambiguous) |

Cleaning result: 100,250 raw rows, 250 duplicates removed, 368 DTI values rescaled, 1,464 employment and 836 utilization values imputed, 100,000 clean rows. Every count is written to `outputs/tables/cleaning_log.csv`.

---

## 3. Protected characteristics and fair lending

No race, ethnicity, religion, sex, sexual orientation, disability, marital status, national origin, age or geographic fields (ZIP code, address) are generated, stored or used. A test (`tests/test_data_generation.py`) fails if a column name suggesting one of these or an obvious proxy is ever added.

Income is used, as it is in real underwriting for ability-to-repay reasons. In a real lending program, even permitted variables would need disparate-impact testing against protected groups before use. That testing is outside the scope of a synthetic project with no demographic data, and this is noted as a limitation.

---

## 4. The Synthetic Risk Score (`src/credit_risk/scoring.py`)

### 4.1 Why logistic regression

The threshold analysis needs one number per applicant that ranks risk. A logistic regression is the standard, transparent choice: each coefficient reads directly as "this factor multiplies the odds of default by X". A more complex model (gradient boosting, neural network) would add little to a threshold analysis and would be harder to explain and govern.

### 4.2 Build steps

1. **Split.** Applicants are randomly split 70% development (69,894) and 30% holdout (30,106) using the fixed seed.
2. **Screen.** A logistic regression is fitted on the development sample with 11 candidate features. A feature is kept only if its p-value is below 0.01 **and** its direction matches credit logic (for example, more delinquencies must mean more risk).
   * Kept (9): credit score, DTI, utilization, recent delinquencies, prior default, recent inquiries, loan-to-income, log income, employment length (capped at 10 years).
   * Dropped (2): credit history length (wrong direction, p = 0.47) and number of open accounts (p = 0.39). This matches the simulation, where neither has a direct effect.
3. **Refit** on the 9 kept features.
4. **Scale to points** using the standard scorecard convention:

   ```
   score = 600 + (20 / ln 2) x ( ln(odds of repaying) - ln 20 )
   ```

   So 600 points means 20-to-1 odds of repaying (4.8% probability of default), and every 20 extra points doubles those odds. **Higher score = lower risk.** Scores range from 331 to 716 in this data (median 591).

### 4.3 What moves the score

From `outputs/tables/score_drivers.csv`:

| Change | Score points |
|---|---:|
| Has a prior default | -18.7 |
| +50 credit score points | +17.4 |
| +1 recent delinquency | -8.9 |
| +10 points of DTI | -6.9 |
| +20 points of card utilization | -6.4 |
| Loan +10% of annual income | -5.4 |
| +5 years employment (to the 10-year cap) | +4.3 |
| Income 50% higher | +4.2 |
| +1 recent credit inquiry | -2.9 |

### 4.4 Validation on the holdout sample

| Measure | Result | What it means |
|---|---|---|
| AUC (holdout) | 0.844 | Picks the defaulter over the non-defaulter 84% of the time in a random pair |
| AUC (development) | 0.844 | Little observed development-to-holdout gap; not proof that overfitting is absent |
| KS (holdout) | 0.52 | Strong separation between defaulters and non-defaulters |
| Predicted vs observed default rate | 13.29% vs 13.19% | Well calibrated overall |
| Calibration by decile | Within 0.7 points in every decile | Well calibrated across the risk range |

See `outputs/figures/07_holdout_calibration.png`.

---

## 5. Approval scenarios (`src/credit_risk/scenarios.py`)

### 5.1 Approval rule and baseline

An applicant is approved when `risk_score >= cutoff`.

The **baseline cutoff is 550**, an assumed current policy that approves about 4 in 5 applicants (81.6%). It is an assumption, not an estimate; the framework works from any starting point, and the Excel workbook lets a reader change it. The 12 scenarios are the baseline plus 11 stricter cutoffs in 5-point steps (550, 555, ..., 605).

### 5.2 Metrics per scenario

| Metric | Definition |
|---|---|
| Applicants approved / declined | Count with score at or above / below the cutoff |
| Approval rate | Approved / 100,000 |
| Approved defaults | Approved applicants with `observed_default = 1` (the default exposure) |
| Default rate | Approved defaults / approved |
| Expected defaults | Sum of predicted PD over approved applicants (model view; tracks observed within 5%) |
| Approved loan volume | Sum of requested amounts for approved applicants |
| Estimated credit loss | Defaulted loan volume x loss given default |
| Expected loss | Sum of PD x loan amount x loss given default (model view) |
| Estimated net contribution | Repaid volume x margin - defaulted volume x loss given default |
| Change vs baseline | Absolute and % change in approvals, defaults and losses |
| Defaults avoided per 100 approvals lost | Cumulative efficiency of tightening |
| Marginal slice | The applicants removed by one 5-point step, and their default rate |

### 5.3 Unit economics (illustrative)

Two assumptions convert default rates into dollars. They are not market data; they are there to make the trade-off concrete, and they are easy to change in the config or the Excel workbook.

* **Net margin on a loan that repays: 12%** of principal over the life of the loan (interest earned minus funding and servicing cost).
* **Loss given default: 75%** of principal (unsecured personal loan).

---

## 6. Decision framework

### 6.1 Why not just minimize defaults

Defaults fall at every step (5,236 at 550 down to 715 at 605), so "fewest defaults" always points to the strictest cutoff, which would turn away over half of current approvals. That answers the wrong question.

### 6.2 The marginal break-even rule

Each 5-point step declines one slice of applicants. For equal-sized loans, a slice with default rate `d` produces, per dollar lent:

```
(1 - d) x margin  -  d x loss given default
```

This is zero when

```
break-even default rate = margin / (margin + loss given default) = 0.12 / 0.87 = 13.8%
```

**Rule:** starting from the baseline, keep tightening while the slice being removed defaults at or above 13.8%. Stop at the first slice that defaults below it.

The implemented decision rule uses a **count-based** default rate. With unequal loan sizes, the exact dollar break-even calculation requires a principal-weighted default rate. The count rule is a screening heuristic, not a general profit optimizer. This project separately computes contribution from each loan's principal and realized outcome. Both methods select 565 in this cohort, but they need not agree under other data or assumptions.

| Step | Score range removed | Default rate of removed slice | Decision |
|---|---|---:|---|
| 550 to 555 | 550-554 | 22.0% | Remove |
| 555 to 560 | 555-559 | 17.1% | Remove |
| 560 to 565 | 560-564 | 15.2% | Remove |
| 565 to 570 | 565-569 | 13.2% | **Stop**: below break-even |

**Recommended cutoff: 565.** See `outputs/figures/03_marginal_slice_vs_break_even.png`.

### 6.3 Cross-checks

* **Dollar view.** Estimated net contribution (same assumptions, loan-size weighted) is highest at 565 ($79.6M vs $75.1M at baseline, +6.0%). The count-based rule and the dollar view agree.
* **Model view.** The score's predicted PD for the 560-564 slice is 15.7% and for 565-569 is 13.6%, telling the same story as the observed outcomes.
* **Holdout subgroup.** Moving from 550 to 565 cuts approvals 12.1% and defaults 33.3% in the model holdout subgroup, close to the full-sample 11.8% and 32.8%. Because cutoff selection uses outcomes from the full portfolio, this is a descriptive subgroup check, not an independent policy evaluation.
* **Diminishing returns.** Defaults avoided per 100 approvals given up fall steadily from 22.0 (first step) to 10.3 (tightening all the way to 605).

### 6.4 Why 565 rather than its neighbours

* **560** leaves in a slice (560-564) that defaults at 15.2%, above break-even: those loans lose money on average.
* **570** removes a slice (565-569) that defaults at 13.2%, just below break-even: those loans are marginally profitable, so declining them gives up 3,698 approvals to avoid 487 defaults.

The 565-569 slice is only about 0.6 points below break-even, and the uncertainty on a slice of about 3,700 applicants is roughly +/- 1 point. So **570 is a reasonable alternative for a lender that wants a margin of safety**, and the recommendation should be presented as "565, with 570 as the cautious option", not as a precise optimum.

### 6.5 Different risk appetites

The rule depends on the lender's economics. Changing only the assumed margin (loss given default held at 75%):

| Risk appetite | Assumed margin | Break-even default rate | Cutoff | Approvals vs baseline | Defaults vs baseline |
|---|---:|---:|---:|---:|---:|
| Conservative | 8% | 9.6% | 580 | -26.3% | -59.7% |
| Base case | 12% | 13.8% | 565 | -11.8% | -32.8% |
| Growth | 16% | 17.6% | 555 | -3.6% | -12.1% |

A lender with thinner margins, higher funding costs, regulatory pressure on loss rates, or a recession outlook would reasonably choose a stricter cutoff. A lender with higher pricing power or a strategic goal of growing market share might accept 555 or 560.

---

## 7. SQL component (`sql/`)

The cleaned, scored applicant table is loaded into SQLite (`data/processed/credit_risk.db`).

* `create_tables.sql` defines the tables with `CHECK` constraints (the database rejects an impossible credit score, for example) and a view, `applicant_segments`, holding every segment band definition.
* `risk_segments.sql` answers: which segments have the highest default rates, which account for the most defaults, where approval volume is concentrated, and which segments absorb the approvals lost when tightening. It uses CTEs, `UNION ALL` unpivoting, and window functions (`SUM() OVER`, running totals).
* `scenario_analysis.sql` recomputes all 12 scenarios with a join to a thresholds table and `LAG()` for marginal slices.

Python executes every query by name. The pipeline stops if the SQL scenario results differ from the pandas results, if any SQL segment dimension fails to sum to 100,000 applicants and 13,260 defaults, or if the SQL band counts differ from an independent pandas banding.

---

## 8. Validation and testing

Two layers:

1. **Pipeline validation checks** (`src/credit_risk/validate.py`) run on every execution and stop the pipeline on failure. They cover record counts, unique IDs, missing values, value ranges, binary fields, designed risk directions, score monotonicity, holdout AUC, overfitting, calibration, scenario monotonicity, scenario reconciliation, and SQL-to-Python reconciliation. Results are saved to `outputs/tables/validation_report.csv`.
2. **Automated tests** (`tests/`, run with `pytest`) run the whole pipeline in a temporary folder and check the outputs, and also deliberately feed broken data to the validators to prove they catch it. A reproducibility test confirms a fresh run matches the committed results exactly, and another confirms the README quotes the current numbers.

---

## 9. Limitations

* **Preprocessing before the split.** Median imputation uses all applicants before the development/holdout split. No holdout outcomes enter model fitting, but the preprocessing is not fully isolated. A strict evaluation would fit imputation only on development data and apply those values to holdout records.
* **Policy selection on the full cohort.** The cutoff is chosen using observed synthetic outcomes from both samples. A separate policy validation sample or a nested split would be needed to estimate performance after cutoff selection.
* **Count-based decision rule.** Principal-weighted contribution is checked separately; agreement in this simulation does not establish that the count-based rule maximizes profit generally.

* **Synthetic data.** Relationships and effect sizes were designed to be plausible, not estimated from real loan performance. The results illustrate a method, not a market.
* **No reject inference problem.** Outcomes are known for every applicant, including those a real lender would have declined. In practice a lender only observes outcomes for approved loans, so the default rate of declined slices must be estimated.
* **Static snapshot.** One application cohort with one outcome per loan. No economic cycle, timing of defaults, prepayment or recoveries over time.
* **Simple economics.** One margin and one loss rate for every loan. Real pricing varies by risk tier, which would shift the break-even line by segment.
* **Single cutoff.** Real policies often add overlays (for example, a DTI cap) on top of a score cutoff.
* **Fair-lending testing not possible.** With no demographic data, disparate-impact testing cannot be done here, but would be required before any real use.
