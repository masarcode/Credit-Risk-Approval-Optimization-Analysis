-- =====================================================================
-- scenario_analysis.sql
-- Independent SQL calculation of every approval scenario. Python computes
-- the same scenarios with pandas and the pipeline fails if they disagree.
-- =====================================================================

-- name: scenario_summary
-- Q: For each cutoff, how many applicants are approved, how many of them
--    default, and what does the approved book look like? The LAG columns
--    describe the "slice" of applicants removed by each tightening step.
WITH s AS (
    SELECT t.scenario_id,
           t.threshold,
           COUNT(a.applicant_id)          AS approved,
           SUM(a.observed_default)        AS approved_defaults,
           AVG(a.observed_default)        AS default_rate,
           SUM(a.requested_loan_amount)   AS approved_loan_volume,
           AVG(a.credit_score)            AS avg_credit_score,
           AVG(a.annual_income)           AS avg_annual_income,
           AVG(a.debt_to_income_ratio)    AS avg_dti
    FROM scenario_thresholds t
    JOIN applicants a ON a.risk_score >= t.threshold
    GROUP BY t.scenario_id, t.threshold
)
SELECT s.*,
       1.0 * approved / (SELECT COUNT(*) FROM applicants)                          AS approval_rate,
       LAG(approved) OVER (ORDER BY threshold) - approved                          AS marginal_declined,
       LAG(approved_defaults) OVER (ORDER BY threshold) - approved_defaults        AS marginal_defaults_avoided,
       1.0 * (LAG(approved_defaults) OVER (ORDER BY threshold) - approved_defaults)
           / (LAG(approved) OVER (ORDER BY threshold) - approved)                  AS marginal_default_rate
FROM s
ORDER BY threshold;

-- name: score_band_distribution
-- Q: How are applicants and defaults distributed across 10-point score
--    bands? Retained as a diagnostic reporting table.
SELECT (risk_score / 10) * 10                 AS score_band_start,
       COUNT(*)                               AS applicants,
       SUM(observed_default)                  AS defaults,
       AVG(observed_default)                  AS default_rate,
       AVG(predicted_pd)                      AS avg_predicted_pd
FROM applicants
GROUP BY score_band_start
ORDER BY score_band_start;
