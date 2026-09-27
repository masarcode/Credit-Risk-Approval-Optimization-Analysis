-- =====================================================================
-- risk_segments.sql
-- Portfolio segmentation queries. Each query starts with a "-- name:"
-- marker so the Python pipeline can run it by name.
-- Parameters: :baseline_threshold, :recommended_threshold
-- =====================================================================

-- name: segment_default_rates
-- Q: Which segments have the highest default rates, and which account for
--    the most defaults? One row per (dimension, band).
WITH long AS (
    SELECT 'Credit score' AS dimension, credit_score_band AS band, credit_score_band_order AS band_order,
           observed_default, risk_score FROM applicant_segments
    UNION ALL
    SELECT 'Income', income_band, income_band_order, observed_default, risk_score FROM applicant_segments
    UNION ALL
    SELECT 'Debt-to-income', dti_band, dti_band_order, observed_default, risk_score FROM applicant_segments
    UNION ALL
    SELECT 'Card utilization', utilization_band, utilization_band_order, observed_default, risk_score FROM applicant_segments
    UNION ALL
    SELECT 'Recent delinquencies', delinquency_band, delinquency_band_order, observed_default, risk_score FROM applicant_segments
    UNION ALL
    SELECT 'Loan size', loan_size_band, loan_size_band_order, observed_default, risk_score FROM applicant_segments
),
agg AS (
    SELECT dimension, band, band_order,
           COUNT(*)                                         AS applicants,
           SUM(observed_default)                            AS defaults,
           AVG(observed_default)                            AS default_rate,
           AVG(risk_score)                                  AS avg_risk_score,
           AVG(risk_score >= :baseline_threshold)           AS baseline_approval_rate,
           AVG(risk_score >= :recommended_threshold)        AS recommended_approval_rate
    FROM long
    GROUP BY dimension, band, band_order
)
SELECT dimension, band, band_order, applicants, defaults, default_rate,
       1.0 * applicants / SUM(applicants) OVER (PARTITION BY dimension) AS share_of_applicants,
       1.0 * defaults   / SUM(defaults)   OVER (PARTITION BY dimension) AS share_of_defaults,
       avg_risk_score, baseline_approval_rate, recommended_approval_rate
FROM agg
ORDER BY dimension, band_order;

-- name: risk_concentration_matrix
-- Q: Where are defaults concentrated when credit score and DTI are
--    combined? Ranked by number of defaults, with cumulative share.
WITH cells AS (
    SELECT credit_score_band, credit_score_band_order, dti_band, dti_band_order,
           COUNT(*)              AS applicants,
           SUM(observed_default) AS defaults,
           AVG(observed_default) AS default_rate
    FROM applicant_segments
    GROUP BY credit_score_band, credit_score_band_order, dti_band, dti_band_order
)
SELECT credit_score_band, credit_score_band_order, dti_band, dti_band_order,
       applicants, defaults, default_rate,
       1.0 * applicants / SUM(applicants) OVER () AS share_of_applicants,
       1.0 * defaults / SUM(defaults) OVER ()     AS share_of_defaults,
       1.0 * SUM(defaults) OVER (ORDER BY defaults DESC, credit_score_band_order, dti_band_order
                                 ROWS UNBOUNDED PRECEDING) / SUM(defaults) OVER () AS cumulative_share_of_defaults
FROM cells
ORDER BY defaults DESC, credit_score_band_order, dti_band_order;

-- name: highest_risk_profiles
-- Q: Which specific borrower profiles (score x DTI x utilization) are the
--    riskiest? Profiles with fewer than 300 applicants are excluded so
--    rates are not driven by tiny samples.
SELECT credit_score_band, dti_band, utilization_band,
       COUNT(*)                                   AS applicants,
       SUM(observed_default)                      AS defaults,
       AVG(observed_default)                      AS default_rate,
       AVG(risk_score)                            AS avg_risk_score,
       AVG(risk_score >= :baseline_threshold)     AS baseline_approval_rate,
       AVG(risk_score >= :recommended_threshold)  AS recommended_approval_rate
FROM applicant_segments
GROUP BY credit_score_band, dti_band, utilization_band
HAVING COUNT(*) >= 300
ORDER BY default_rate DESC
LIMIT 10;

-- name: tightening_impact
-- Q: Where is approval volume concentrated today, and which segments
--    absorb the approvals lost when moving to the recommended cutoff?
WITH long AS (
    SELECT 'Credit score' AS dimension, credit_score_band AS band, credit_score_band_order AS band_order,
           observed_default, risk_score FROM applicant_segments
    UNION ALL
    SELECT 'Income', income_band, income_band_order, observed_default, risk_score FROM applicant_segments
    UNION ALL
    SELECT 'Debt-to-income', dti_band, dti_band_order, observed_default, risk_score FROM applicant_segments
    UNION ALL
    SELECT 'Card utilization', utilization_band, utilization_band_order, observed_default, risk_score FROM applicant_segments
    UNION ALL
    SELECT 'Recent delinquencies', delinquency_band, delinquency_band_order, observed_default, risk_score FROM applicant_segments
    UNION ALL
    SELECT 'Loan size', loan_size_band, loan_size_band_order, observed_default, risk_score FROM applicant_segments
),
agg AS (
    SELECT dimension, band, band_order,
           SUM(risk_score >= :baseline_threshold)                                  AS baseline_approved,
           SUM(risk_score >= :recommended_threshold)                               AS recommended_approved,
           SUM(risk_score >= :baseline_threshold AND risk_score < :recommended_threshold) AS approvals_lost,
           SUM(CASE WHEN risk_score >= :baseline_threshold AND risk_score < :recommended_threshold
                    THEN observed_default ELSE 0 END)                              AS defaults_avoided
    FROM long
    GROUP BY dimension, band, band_order
)
SELECT dimension, band, band_order, baseline_approved, recommended_approved,
       approvals_lost, defaults_avoided,
       1.0 * baseline_approved / SUM(baseline_approved) OVER (PARTITION BY dimension) AS share_of_baseline_approvals,
       1.0 * approvals_lost / NULLIF(baseline_approved, 0)                            AS pct_of_band_approvals_lost,
       1.0 * approvals_lost / SUM(approvals_lost) OVER (PARTITION BY dimension)       AS share_of_all_approvals_lost,
       1.0 * defaults_avoided / NULLIF(approvals_lost, 0)                             AS default_rate_of_declined
FROM agg
ORDER BY dimension, band_order;
