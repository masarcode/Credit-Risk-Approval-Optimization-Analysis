"""Rebuild charts, Excel workbook and the executive summary
from the saved result tables, without re-running the analysis.

    python scripts/build_outputs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from credit_risk.config import REPO_ROOT, load_config  # noqa: E402
from credit_risk.reporting import build_outputs  # noqa: E402

if __name__ == "__main__":
    build_outputs(REPO_ROOT, load_config())
    print("Outputs rebuilt.")
