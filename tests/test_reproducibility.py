"""A fresh run must reproduce the committed results exactly, and the README
must quote the committed results."""
import json

import pytest


@pytest.fixture(scope="module")
def committed(repo_root):
    path = repo_root / "outputs/tables/headline_metrics.json"
    if not path.exists():
        pytest.skip("Run scripts/run_pipeline.py first to create committed outputs")
    return json.loads(path.read_text())


KEYS = ["baseline_threshold", "recommended_threshold", "baseline_approved", "recommended_approved",
        "baseline_defaults", "recommended_defaults", "n_scenarios", "validation_checks_total"]


def test_fresh_run_reproduces_committed_headline(run, committed):
    for k in KEYS:
        assert run["headline"][k] == committed[k], k
    assert run["headline"]["pct_change_defaults"] == pytest.approx(committed["pct_change_defaults"], abs=1e-12)
    assert run["headline"]["model"]["auc_holdout"] == pytest.approx(committed["model"]["auc_holdout"], abs=1e-12)


def test_readme_quotes_current_results(repo_root, committed):
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    h = committed
    expected = [
        f"{h['baseline_threshold']}", f"{h['recommended_threshold']}",
        f"{h['baseline_approval_rate']:.1%}", f"{h['recommended_approval_rate']:.1%}",
        f"{-h['pct_change_approvals']:.1%}", f"{-h['pct_change_defaults']:.1%}",
        f"{h['baseline_defaults']:,}", f"{h['recommended_defaults']:,}",
        f"{h['baseline_default_rate']:.1%}", f"{h['recommended_default_rate']:.1%}",
    ]
    missing = [e for e in expected if e not in readme]
    assert not missing, f"README is out of date; missing {missing}"


def test_recruiter_facing_text_has_no_em_dashes(repo_root):
    files = ["README.md", "docs/methodology.md", "docs/data_dictionary.md",
             "outputs/executive_summary/executive_summary.md"]
    for f in files:
        p = repo_root / f
        if p.exists():
            assert "\u2014" not in p.read_text(encoding="utf-8"), f
