import json
import re

import pandas as pd
from openpyxl import load_workbook

from credit_risk.data_dictionary import FIELDS
from credit_risk.segmentation import DB_COLUMNS


def test_expected_files_exist(run, config):
    root = run["root"]
    expected = [
        config["paths"]["raw_data"], config["paths"]["processed_data"], config["paths"]["scored_data"],
        config["paths"]["database"], "outputs/tables/headline_metrics.json",
        "outputs/tables/scenario_results.csv", "outputs/excel/credit_risk_decision_workbook.xlsx",
        "outputs/executive_summary/executive_summary.pdf", "outputs/executive_summary/executive_summary.md",
        "outputs/figures/portfolio_dashboard.svg",
    ]
    for rel in expected:
        p = root / rel
        assert p.exists() and p.stat().st_size > 0, rel
    figures = root / "outputs/figures"
    assert len(list(figures.glob("*.png"))) == 6


def test_pdf_is_a_single_page(run):
    data = (run["root"] / "outputs/executive_summary/executive_summary.pdf").read_bytes()
    assert data.startswith(b"%PDF")
    pages = re.findall(rb"/Type\s*/Page(?!s)", data)
    assert len(pages) == 1


def test_excel_workbook_structure_and_formulas(run):
    wb = load_workbook(run["root"] / "outputs/excel/credit_risk_decision_workbook.xlsx")
    assert wb.sheetnames[:4] == ["Executive Summary", "Scenario Analysis", "Segment Risk", "Score Drivers"]
    assert "Data Dictionary" in wb.sheetnames
    es, sc = wb["Executive Summary"], wb["Scenario Analysis"]
    assert es["C5"].value == run["headline"]["baseline_threshold"]
    assert str(es["C8"].value).startswith("=")                     # break-even is a formula
    assert "SUMPRODUCT" in str(es["C12"].value)                      # recommendation is a formula
    assert sc["C5"].value == 550 and sc["C16"].value == 605          # 12 scenario rows
    assert str(sc["F5"].value).startswith("=")                       # approval rate is a formula
    assert sc["D5"].value == run["headline"]["baseline_approved"]


def test_portfolio_overview_exists(run):
    from xml.etree import ElementTree as ET
    path = run["root"] / "outputs/figures/portfolio_dashboard.svg"
    root = ET.parse(path).getroot()
    assert root.tag.endswith("svg")
    content = path.read_text()
    assert f"Raise the cutoff from {run['headline']['baseline_threshold']} to {run['headline']['recommended_threshold']}" in content


def test_headline_matches_scenario_table(run, config):
    h = json.loads((run["root"] / "outputs/tables/headline_metrics.json").read_text())
    s = run["scenarios"].set_index("threshold")
    r = s.loc[h["recommended_threshold"]]
    assert h["recommended_approved"] == r["approved"]
    assert h["recommended_defaults"] == r["approved_defaults"]
    assert h["n_scenarios"] == 12


def test_data_dictionary_covers_every_field(run):
    documented = {f[0] for f in FIELDS}
    assert set(DB_COLUMNS) <= documented
    assert set(run["scored"].columns) <= documented
