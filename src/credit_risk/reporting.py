"""Build every stakeholder-facing output from the saved result tables.

Outputs are rebuilt from ``outputs/tables`` (not recomputed), so
``scripts/build_outputs.py`` can refresh charts, the workbook and the
executive summary in a few seconds.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from . import charts, portfolio_visual, data_dictionary, excel_report, executive_summary


def _read_segments(path: Path) -> pd.DataFrame:
    # Band labels such as "None" and "1" must stay text, not become NaN / numbers
    return pd.read_csv(path, keep_default_na=False, dtype={"band": str})


def load_tables(root: Path, config: dict) -> tuple[dict, dict]:
    t = root / config["paths"]["tables_dir"]
    with open(t / "headline_metrics.json", encoding="utf-8") as f:
        headline = json.load(f)
    tables = {
        "scenarios": pd.read_csv(t / "scenario_results.csv"),
        "segments": _read_segments(t / "sql_segment_default_rates.csv"),
        "matrix": pd.read_csv(t / "sql_risk_concentration_matrix.csv"),
        "profiles": pd.read_csv(t / "sql_highest_risk_profiles.csv"),
        "tightening": _read_segments(t / "sql_tightening_impact.csv"),
        "score_bands": pd.read_csv(t / "sql_score_band_distribution.csv"),
        "sensitivity": pd.read_csv(t / "risk_appetite_sensitivity.csv"),
        "drivers": pd.read_csv(t / "score_drivers.csv"),
        "screening": pd.read_csv(t / "model_feature_screening.csv"),
        "calibration": pd.read_csv(t / "holdout_calibration.csv"),
        "validation": pd.read_csv(t / "validation_report.csv"),
    }
    return tables, headline


def build_outputs(root: Path, config: dict, verbose: bool = True) -> dict[str, list[Path]]:
    say = print if verbose else (lambda *a, **k: None)
    tables, headline = load_tables(root, config)
    p = {k: root / v for k, v in config["paths"].items()}

    say("Building charts ...")
    figs = charts.build_all(tables, headline, config, p["figures_dir"])
    say("Building portfolio overview ...")
    overview = portfolio_visual.build(tables, headline, config, p["figures_dir"])
    say("Writing Excel workbook ...")
    xlsx = excel_report.build_workbook(tables, headline, config, p["excel_dir"] / "credit_risk_decision_workbook.xlsx")
    say("Writing executive summary ...")
    summary = executive_summary.build(tables, headline, config, p["summary_dir"], p["figures_dir"])
    docs = [data_dictionary.write_markdown(root / "docs" / "data_dictionary.md", config)]
    return {"docs": docs, "figures": figs + overview,
            "excel": [xlsx], "summary": summary}
