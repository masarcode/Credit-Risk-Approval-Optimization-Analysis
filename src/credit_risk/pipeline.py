"""End-to-end analysis: generate -> validate -> clean -> score -> SQLite ->
scenarios -> SQL segmentation -> reconciliation -> saved result tables.

``run_analysis`` writes everything relative to ``root`` so the tests can run
the full pipeline in a temporary folder without touching the repository.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import validate as v
from .clean import clean_applications
from .generate_data import generate
from .scenarios import (compute_scenarios, holdout_check, recommend,
                        risk_appetite_sensitivity, thresholds)
from .scoring import build_score
from .segmentation import build_database, python_segments, run_sql_file


class ValidationError(RuntimeError):
    pass


def _raise_on_failure(checks: list[v.Check], stage: str) -> None:
    failed = [c for c in checks if not c.passed]
    if failed:
        lines = "\n".join(f"  - {c.check}: {c.detail}" for c in failed)
        raise ValidationError(f"Validation failed at stage '{stage}':\n{lines}")


def run_analysis(config: dict, root: Path, sql_dir: Path, verbose: bool = True) -> dict:
    p = {k: root / val for k, val in config["paths"].items() if k != "sql_dir"}
    for key in ["raw_data", "processed_data", "database"]:
        p[key].parent.mkdir(parents=True, exist_ok=True)
    p["tables_dir"].mkdir(parents=True, exist_ok=True)
    say = print if verbose else (lambda *a, **k: None)
    checks: list[v.Check] = []

    say("[1/7] Generating synthetic applications ...")
    raw = generate(config)
    raw.to_csv(p["raw_data"], index=False)
    c = v.validate_raw(raw, config); checks += c; _raise_on_failure(c, "raw")

    say("[2/7] Cleaning and validating ...")
    clean, clean_log = clean_applications(raw)
    clean.to_csv(p["processed_data"], index=False)
    c = v.validate_clean(clean, config); checks += c; _raise_on_failure(c, "clean")

    say("[3/7] Building the Synthetic Risk Score ...")
    scored, model_summary, screening, drivers, calibration = build_score(clean, config)
    scored.to_csv(p["scored_data"], index=False)
    c = v.validate_scored(scored, model_summary); checks += c; _raise_on_failure(c, "score")

    say("[4/7] Loading SQLite database ...")
    grid = thresholds(config)
    build_database(scored, p["database"], sql_dir, grid)

    say("[5/7] Calculating approval scenarios ...")
    scen = compute_scenarios(scored, config)
    c = v.validate_scenarios(scen, scored, config); checks += c; _raise_on_failure(c, "scenarios")
    be = float(scen["break_even_default_rate"].iloc[0])
    rec = recommend(scen, be)
    sensitivity = risk_appetite_sensitivity(scen, config)
    base_t = config["scenarios"]["baseline_threshold"]
    holdout = holdout_check(scored, base_t, rec["threshold"])

    say("[6/7] Running SQL segmentation and reconciliation ...")
    params = {"baseline_threshold": base_t, "recommended_threshold": rec["threshold"]}
    seg = run_sql_file(p["database"], sql_dir / "risk_segments.sql", params)
    sql_scen = run_sql_file(p["database"], sql_dir / "scenario_analysis.sql")
    c = (v.validate_sql_reconciliation(sql_scen["scenario_summary"], scen, seg["segment_default_rates"], scored)
         + v.validate_segment_parity(seg["segment_default_rates"][["dimension", "band", "applicants", "defaults"]],
                                     python_segments(scored, config)))
    checks += c; _raise_on_failure(c, "sql")

    say("[7/7] Saving result tables ...")
    t = p["tables_dir"]
    pd.DataFrame([clean_log]).T.rename(columns={0: "value"}).rename_axis("item").to_csv(t / "cleaning_log.csv")
    screening.to_csv(t / "model_feature_screening.csv", index=False)
    drivers.to_csv(t / "score_drivers.csv", index=False)
    calibration.to_csv(t / "holdout_calibration.csv", index=False)
    scen.to_csv(t / "scenario_results.csv", index=False)
    sensitivity.to_csv(t / "risk_appetite_sensitivity.csv", index=False)
    for name, frame in {**seg, **sql_scen}.items():
        frame.to_csv(t / f"sql_{name}.csv", index=False)
    val = v.to_frame(checks)
    val.to_csv(t / "validation_report.csv", index=False)

    b, r = scen.iloc[0], scen.iloc[rec["index"]]
    headline = {
        "n_applicants": int(len(scored)),
        "n_scenarios": int(len(scen)),
        "overall_default_rate": float(scored["observed_default"].mean()),
        "baseline_threshold": int(b["threshold"]),
        "recommended_threshold": int(r["threshold"]),
        "points_tightened": int(r["threshold"] - b["threshold"]),
        "baseline_approved": int(b["approved"]),
        "recommended_approved": int(r["approved"]),
        "baseline_approval_rate": float(b["approval_rate"]),
        "recommended_approval_rate": float(r["approval_rate"]),
        "pct_change_approvals": float(r["pct_change_approvals"]),
        "baseline_defaults": int(b["approved_defaults"]),
        "recommended_defaults": int(r["approved_defaults"]),
        "pct_change_defaults": float(r["pct_change_defaults"]),
        "baseline_default_rate": float(b["default_rate"]),
        "recommended_default_rate": float(r["default_rate"]),
        "baseline_expected_defaults": float(b["expected_defaults"]),
        "recommended_expected_defaults": float(r["expected_defaults"]),
        "baseline_credit_loss": float(b["estimated_credit_loss"]),
        "recommended_credit_loss": float(r["estimated_credit_loss"]),
        "pct_change_credit_loss": float(r["pct_change_credit_loss"]),
        "baseline_net_contribution": float(b["est_net_contribution"]),
        "recommended_net_contribution": float(r["est_net_contribution"]),
        "pct_change_net_contribution": float(r["pct_change_net_contribution"]),
        "max_net_contribution_threshold": int(scen.loc[scen["est_net_contribution"].idxmax(), "threshold"]),
        "break_even_default_rate": be,
        "defaults_avoided_per_100_approvals_lost": float(r["defaults_avoided_per_100_approvals_lost"]),
        "next_slice_default_rate": float(scen.iloc[rec["index"] + 1]["marginal_default_rate"])
        if rec["index"] + 1 < len(scen) else None,
        "last_cut_slice_default_rate": float(r["marginal_default_rate"]) if rec["index"] > 0 else None,
        "model": model_summary,
        "holdout_check": holdout,
        "validation_checks_total": int(len(val)),
        "validation_checks_passed": int(val["passed"].sum()),
        "cleaning": clean_log,
    }
    with open(t / "headline_metrics.json", "w", encoding="utf-8") as f:
        json.dump(headline, f, indent=2, default=float)

    say(f"      {int(val['passed'].sum())}/{len(val)} validation checks passed")
    return {"scored": scored, "scenarios": scen, "headline": headline, "segments": seg,
            "sql_scenarios": sql_scen, "validation": val, "sensitivity": sensitivity,
            "drivers": drivers, "screening": screening, "calibration": calibration}
