import sqlite3

import pytest

from credit_risk.segmentation import read_named_queries


def _db(run, config):
    return run["root"] / config["paths"]["database"]


def test_sql_files_define_expected_queries(repo_root):
    seg = read_named_queries(repo_root / "sql" / "risk_segments.sql")
    scen = read_named_queries(repo_root / "sql" / "scenario_analysis.sql")
    assert {"segment_default_rates", "risk_concentration_matrix", "highest_risk_profiles",
            "tightening_impact"} <= set(seg)
    assert {"scenario_summary", "score_band_distribution"} <= set(scen)


def test_database_row_counts(run, config):
    with sqlite3.connect(_db(run, config)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM applicants").fetchone()[0] == 100_000
        assert conn.execute("SELECT COUNT(DISTINCT applicant_id) FROM applicants").fetchone()[0] == 100_000
        assert conn.execute("SELECT COUNT(*) FROM scenario_thresholds").fetchone()[0] == 12
        assert conn.execute("SELECT COUNT(*) FROM applicant_segments").fetchone()[0] == 100_000


def test_database_constraints_reject_impossible_values(run, config):
    with sqlite3.connect(_db(run, config)) as conn:
        row = conn.execute("SELECT * FROM applicants LIMIT 1").fetchone()
        cols = [d[0] for d in conn.execute("SELECT * FROM applicants LIMIT 1").description]
        bad = dict(zip(cols, row))
        bad["applicant_id"] = "APP-TEST"
        bad["credit_score"] = 900
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"INSERT INTO applicants ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                         list(bad.values()))


def test_sql_scenarios_match_python_exactly(run):
    sql = run["sql_scenarios"]["scenario_summary"].set_index("threshold")
    py = run["scenarios"].set_index("threshold")
    assert (sql["approved"] == py["approved"]).all()
    assert (sql["approved_defaults"] == py["approved_defaults"]).all()
    assert (sql["approval_rate"] - py["approval_rate"]).abs().max() < 1e-12
    assert (sql["avg_credit_score"] - py["avg_credit_score"]).abs().max() < 1e-9
    m = sql["marginal_default_rate"].dropna() - py["marginal_default_rate"].dropna()
    assert m.abs().max() < 1e-12


def test_sql_segments_reconcile_to_totals(run):
    seg = run["segments"]["segment_default_rates"]
    n, d = len(run["scored"]), int(run["scored"]["observed_default"].sum())
    for _, g in seg.groupby("dimension"):
        assert g["applicants"].sum() == n
        assert g["defaults"].sum() == d
        assert g["share_of_defaults"].sum() == pytest.approx(1.0)


def test_sql_band_labels_match_config(run, config):
    seg = run["segments"]["segment_default_rates"]
    mapping = {"Credit score": "credit_score_band", "Income": "income_band", "Debt-to-income": "dti_band",
               "Card utilization": "utilization_band", "Recent delinquencies": "delinquency_band",
               "Loan size": "loan_size_band"}
    for dim, key in mapping.items():
        got = seg[seg["dimension"] == dim].sort_values("band_order")["band"].tolist()
        assert got == config["segments"][key]["labels"]


def test_tightening_impact_reconciles_to_scenarios(run):
    t = run["segments"]["tightening_impact"]
    h = run["headline"]
    for _, g in t.groupby("dimension"):
        assert g["approvals_lost"].sum() == h["baseline_approved"] - h["recommended_approved"]
        assert g["defaults_avoided"].sum() == h["baseline_defaults"] - h["recommended_defaults"]
        assert g["baseline_approved"].sum() == h["baseline_approved"]


def test_concentration_matrix_cumulative_share(run):
    m = run["segments"]["risk_concentration_matrix"]
    assert m["cumulative_share_of_defaults"].is_monotonic_increasing
    assert m["cumulative_share_of_defaults"].iloc[-1] == pytest.approx(1.0)
