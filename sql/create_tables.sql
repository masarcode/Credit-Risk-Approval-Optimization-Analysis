-- =====================================================================
-- create_tables.sql
-- Builds the SQLite analysis database.
--   applicants            : one row per applicant (cleaned + scored)
--   scenario_thresholds   : the 12 approval cutoffs being evaluated
--   applicant_segments    : view that adds the business segment bands
-- CHECK constraints make the database itself reject impossible values.
-- =====================================================================

DROP VIEW IF EXISTS applicant_segments;
DROP TABLE IF EXISTS applicants;
DROP TABLE IF EXISTS scenario_thresholds;

CREATE TABLE applicants (
    applicant_id                        TEXT PRIMARY KEY,
    annual_income                       REAL    NOT NULL CHECK (annual_income > 0),
    employment_length                   REAL    NOT NULL CHECK (employment_length >= 0),
    credit_score                        INTEGER NOT NULL CHECK (credit_score BETWEEN 300 AND 850),
    credit_history_length               REAL    NOT NULL CHECK (credit_history_length >= 0),
    number_of_open_accounts             INTEGER NOT NULL CHECK (number_of_open_accounts >= 0),
    revolving_utilization               REAL    NOT NULL CHECK (revolving_utilization BETWEEN 0 AND 1),
    recent_delinquencies                INTEGER NOT NULL CHECK (recent_delinquencies >= 0),
    recent_credit_inquiries             INTEGER NOT NULL CHECK (recent_credit_inquiries >= 0),
    previous_default_flag               INTEGER NOT NULL CHECK (previous_default_flag IN (0, 1)),
    debt_to_income_ratio                REAL    NOT NULL CHECK (debt_to_income_ratio BETWEEN 0 AND 0.60),
    existing_debt                       REAL    NOT NULL CHECK (existing_debt >= 0),
    requested_loan_amount               REAL    NOT NULL CHECK (requested_loan_amount > 0),
    observed_default                    INTEGER NOT NULL CHECK (observed_default IN (0, 1)),
    employment_length_imputed_flag      INTEGER NOT NULL CHECK (employment_length_imputed_flag IN (0, 1)),
    revolving_utilization_imputed_flag  INTEGER NOT NULL CHECK (revolving_utilization_imputed_flag IN (0, 1)),
    loan_to_income_ratio                REAL    NOT NULL,
    sample                              TEXT    NOT NULL CHECK (sample IN ('development', 'holdout')),
    predicted_pd                        REAL    NOT NULL CHECK (predicted_pd > 0 AND predicted_pd < 1),
    risk_score                          INTEGER NOT NULL
);

CREATE INDEX idx_applicants_risk_score ON applicants (risk_score);

CREATE TABLE scenario_thresholds (
    scenario_id  TEXT PRIMARY KEY,
    threshold    INTEGER NOT NULL UNIQUE
);

-- Segment bands. Intervals are closed on the left and open on the right,
-- e.g. '620-659' means 620 <= credit_score < 660. These definitions are
-- mirrored in config/analysis_config.yaml and a test checks they agree.
CREATE VIEW applicant_segments AS
SELECT
    a.*,
    CASE WHEN credit_score < 580 THEN '<580'
         WHEN credit_score < 620 THEN '580-619'
         WHEN credit_score < 660 THEN '620-659'
         WHEN credit_score < 700 THEN '660-699'
         WHEN credit_score < 740 THEN '700-739'
         ELSE '740+' END                                   AS credit_score_band,
    CASE WHEN credit_score < 580 THEN 1 WHEN credit_score < 620 THEN 2
         WHEN credit_score < 660 THEN 3 WHEN credit_score < 700 THEN 4
         WHEN credit_score < 740 THEN 5 ELSE 6 END         AS credit_score_band_order,

    CASE WHEN annual_income < 35000  THEN '<$35K'
         WHEN annual_income < 50000  THEN '$35K-49K'
         WHEN annual_income < 75000  THEN '$50K-74K'
         WHEN annual_income < 100000 THEN '$75K-99K'
         WHEN annual_income < 150000 THEN '$100K-149K'
         ELSE '$150K+' END                                 AS income_band,
    CASE WHEN annual_income < 35000 THEN 1 WHEN annual_income < 50000 THEN 2
         WHEN annual_income < 75000 THEN 3 WHEN annual_income < 100000 THEN 4
         WHEN annual_income < 150000 THEN 5 ELSE 6 END     AS income_band_order,

    CASE WHEN debt_to_income_ratio < 0.10 THEN '<10%'
         WHEN debt_to_income_ratio < 0.20 THEN '10-19%'
         WHEN debt_to_income_ratio < 0.30 THEN '20-29%'
         WHEN debt_to_income_ratio < 0.40 THEN '30-39%'
         ELSE '40%+' END                                   AS dti_band,
    CASE WHEN debt_to_income_ratio < 0.10 THEN 1 WHEN debt_to_income_ratio < 0.20 THEN 2
         WHEN debt_to_income_ratio < 0.30 THEN 3 WHEN debt_to_income_ratio < 0.40 THEN 4
         ELSE 5 END                                        AS dti_band_order,

    CASE WHEN revolving_utilization < 0.30 THEN '<30%'
         WHEN revolving_utilization < 0.50 THEN '30-49%'
         WHEN revolving_utilization < 0.70 THEN '50-69%'
         WHEN revolving_utilization < 0.90 THEN '70-89%'
         ELSE '90%+' END                                   AS utilization_band,
    CASE WHEN revolving_utilization < 0.30 THEN 1 WHEN revolving_utilization < 0.50 THEN 2
         WHEN revolving_utilization < 0.70 THEN 3 WHEN revolving_utilization < 0.90 THEN 4
         ELSE 5 END                                        AS utilization_band_order,

    CASE WHEN recent_delinquencies = 0 THEN 'None'
         WHEN recent_delinquencies = 1 THEN '1'
         ELSE '2+' END                                     AS delinquency_band,
    CASE WHEN recent_delinquencies = 0 THEN 1
         WHEN recent_delinquencies = 1 THEN 2 ELSE 3 END   AS delinquency_band_order,

    CASE WHEN requested_loan_amount < 5000  THEN '<$5K'
         WHEN requested_loan_amount < 10000 THEN '$5K-9.9K'
         WHEN requested_loan_amount < 20000 THEN '$10K-19.9K'
         WHEN requested_loan_amount < 30000 THEN '$20K-29.9K'
         ELSE '$30K+' END                                  AS loan_size_band,
    CASE WHEN requested_loan_amount < 5000 THEN 1 WHEN requested_loan_amount < 10000 THEN 2
         WHEN requested_loan_amount < 20000 THEN 3 WHEN requested_loan_amount < 30000 THEN 4
         ELSE 5 END                                        AS loan_size_band_order
FROM applicants a;
