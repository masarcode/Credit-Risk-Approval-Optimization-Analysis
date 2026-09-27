# Verification notes

Reviewed on September 26, 2026 with Python 3.12 and the pinned dependencies in `requirements.txt`.

## Pipeline and tests

The full pipeline completed with **38 of 38 validation checks passing**. The automated suite passed **57 tests**, including a fresh pipeline run, Python/SQL reconciliation, malformed-input cases, generated-file checks and comparison with committed headline metrics.

The verification commands are:

```bash
python scripts/run_pipeline.py
python -m pytest
```

These are local verification results. The Actions badge reports GitHub's separate CI status.

## Verified base case

| Metric | Baseline | Recommended |
|---|---:|---:|
| Synthetic Risk Score cutoff | 550 | 565 |
| Approved applicants | 81,583 | 71,966 |
| Approval rate | 81.583% | 71.966% |
| Defaults among approved applicants | 5,236 | 3,518 |
| Approved default rate | 6.418% | 4.888% |
| Estimated credit loss | $53,017,687.50 | $35,854,875.00 |
| Estimated lifetime net contribution | $75,140,782.50 | $79,646,505.00 |

Approval volume falls 11.788%; approved defaults fall 32.811%; estimated contribution rises 5.996%. Holdout AUC is 0.844145. The cohort contains 100,000 applicants and the grid contains 12 cutoffs from 550 to 605.

Sources: `outputs/tables/headline_metrics.json`, `scenario_results.csv`, `sql_scenario_summary.csv` and `validation_report.csv`.

## Excel calculation review

The workbook was imported and recalculated in a separate spreadsheet calculation engine. All 12 scenario rows were compared with the Python reporting tables and independently calculated economics. Checks covered counts, rates, loan volumes, credit loss, contribution, baseline changes, marginal counts and marginal default rates. The base-case error scan returned no formula errors. All five sheets were rendered for layout review.

The following inputs were exercised in memory, then restored to the base case:

| Baseline | Lifetime margin | Loss given default | Recalculated cutoff |
|---|---:|---:|---:|
| 550 | 12% | 75% | 565 |
| 550 | 8% | 75% | 580 |
| 550 | 16% | 75% | 555 |
| 550 | 12% | 50% | 555 |
| 550 | 12% | 90% | 570 |
| 570 | 12% | 75% | 570 |
| 605 | 12% | 75% | 605 |
| 550 | 0% | 75% | 605 |
| 550 | 100% | 75% | 550 |

The final two cases test calculation boundaries, not plausible lending economics. Recommendation text now distinguishes retaining the baseline from raising it and identifies the highest tested cutoff without claiming that an untested next group fails the rule. Input validation limits the baseline to the grid, margin to 0%-100%, and loss given default to a positive value up to 100%.

Native Microsoft Excel was not available for this review. The workbook preserves its original formulas and requests recalculation on opening; it does not contain precomputed Excel formula caches. Recalculate in Excel before reading formula results. Spreadsheet previews that do not calculate formulas may show blanks. The independent calculation check is not a claim of native Excel certification.

## Presentation and methodology review

The repository contains six distinct visuals, a one-page PDF briefing and the Excel workbook. The overview is available as both SVG and PNG. Figures and the PDF were rendered and inspected; Markdown links were checked against the final files.

The analytical model and generated cohort were preserved. The presentation now makes three qualifications explicit:

1. Median imputation occurs before the development/holdout split, so preprocessing uses information from the full sample.
2. The cutoff is selected using full-cohort outcomes. Policy results for the holdout subgroup are descriptive, not an independent evaluation of the selected policy.
3. The stopping rule uses applicant counts, while contribution weights outcomes by loan principal. Both select 565 here; they need not agree in another portfolio.

Contribution is an illustrative lifetime amount under uniform economics, not a forecast of bank profit. Similar development and holdout AUCs are reported as a small measured performance gap, not proof that overfitting is absent.
