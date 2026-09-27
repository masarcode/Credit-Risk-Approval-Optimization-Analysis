"""Shared fixtures.

The full pipeline is run ONCE per test session in a temporary folder, so the
tests never depend on (or overwrite) files in the repository.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from credit_risk.config import load_config  # noqa: E402
from credit_risk.pipeline import run_analysis  # noqa: E402
from credit_risk.reporting import build_outputs  # noqa: E402


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def run(config, tmp_path_factory):
    root = tmp_path_factory.mktemp("pipeline_run")
    result = run_analysis(config, root, REPO / "sql", verbose=False)
    outputs = build_outputs(root, config, verbose=False)
    return {"root": root, "outputs": outputs, **result}


@pytest.fixture(scope="session")
def repo_root():
    return REPO
