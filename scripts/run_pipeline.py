"""Run the full project from scratch.

    python scripts/run_pipeline.py

Steps: generate synthetic data -> validate -> clean -> score -> load SQLite
-> scenarios -> SQL segmentation + reconciliation -> charts, Excel workbook,
static figures and executive summary.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from credit_risk.config import REPO_ROOT, load_config  # noqa: E402
from credit_risk.pipeline import run_analysis  # noqa: E402
from credit_risk.reporting import build_outputs  # noqa: E402


def main() -> None:
    start = time.time()
    config = load_config()
    result = run_analysis(config, REPO_ROOT, REPO_ROOT / config["paths"]["sql_dir"])
    build_outputs(REPO_ROOT, config)
    h = result["headline"]
    print("\nHeadline results")
    print(f"  Baseline cutoff {h['baseline_threshold']}  -> recommended cutoff {h['recommended_threshold']}")
    print(f"  Approval rate   {h['baseline_approval_rate']:.1%} -> {h['recommended_approval_rate']:.1%} "
          f"({h['pct_change_approvals']:+.1%} approvals)")
    print(f"  Defaults        {h['baseline_defaults']:,} -> {h['recommended_defaults']:,} "
          f"({h['pct_change_defaults']:+.1%})")
    print(f"  Validation      {h['validation_checks_passed']}/{h['validation_checks_total']} checks passed")
    print(f"Done in {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
