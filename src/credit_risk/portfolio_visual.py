"""Compact portfolio overview built from the same tables as the analysis."""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, FuncFormatter

NAVY = "#183650"
BLUE = "#2A78D6"
ORANGE = "#C95832"
MUTED = "#59636C"
GRID = "#E1E6EB"


def build(tables: dict, h: dict, config: dict, out_dir: Path) -> list[Path]:
    s = tables["scenarios"]
    fig = plt.figure(figsize=(13, 7.6), facecolor="white")
    fig.text(.055, .955, "CREDIT RISK / APPROVAL POLICY", fontsize=10, color=MUTED)
    fig.text(.055, .900, f"Raise the cutoff from {h['baseline_threshold']} to {h['recommended_threshold']}",
             fontsize=27, weight="bold", color=NAVY)
    fig.text(.055, .853, "Fewer approved defaults, with a smaller reduction in approval volume.",
             fontsize=12, color=MUTED)

    metrics = [
        ("APPROVAL VOLUME", f"{h['pct_change_approvals']:+.1%}",
         f"{h['baseline_approved']:,} to {h['recommended_approved']:,}"),
        ("APPROVED DEFAULTS", f"{h['pct_change_defaults']:+.1%}",
         f"{h['baseline_defaults']:,} to {h['recommended_defaults']:,}"),
        ("APPROVED DEFAULT RATE", f"{h['recommended_default_rate']:.1%}",
         f"from {h['baseline_default_rate']:.1%} at baseline"),
        ("EST. NET CONTRIBUTION", f"{h['pct_change_net_contribution']:+.1%}",
         f"${h['baseline_net_contribution']/1e6:.1f}M to ${h['recommended_net_contribution']/1e6:.1f}M"),
    ]
    for i, (label, value, note) in enumerate(metrics):
        x = .055 + i * .233
        fig.text(x, .770, label, fontsize=9, color=MUTED)
        fig.text(x, .707, value, fontsize=27, weight="bold", color=NAVY)
        fig.text(x, .670, note, fontsize=10, color=MUTED, parse_math=False)
    left = fig.add_axes([.08, .215, .39, .32])
    left.plot(s.threshold, -s.pct_change_defaults, color=ORANGE, lw=2.6,
              marker="o", ms=4, label="Defaults avoided")
    left.plot(s.threshold, -s.pct_change_approvals, color=BLUE, lw=2.6,
              marker="o", ms=4, label="Approvals given up")
    left.axvline(h["recommended_threshold"], color=NAVY, ls="--", lw=1)
    left.set_title("Defaults fall faster than approvals", fontsize=13, pad=14)
    left.set_xlabel("Approval cutoff (Synthetic Risk Score)")
    left.set_ylabel("Reduction vs baseline")
    left.yaxis.set_major_formatter(PercentFormatter(1))
    left.set_ylim(0, 1)
    left.legend(frameon=False, fontsize=9, loc="upper left")
    right = fig.add_axes([.59, .215, .35, .32])
    right.plot(s.threshold, s.est_net_contribution / 1e6, color=NAVY, lw=2.6,
               marker="o", ms=4)
    r = s[s.threshold == h["recommended_threshold"]].iloc[0]
    right.scatter([r.threshold], [r.est_net_contribution / 1e6], s=95, color=BLUE, zorder=4)
    right.annotate(f"{h['recommended_threshold']}: ${r.est_net_contribution/1e6:.1f}M",
                   (r.threshold, r.est_net_contribution/1e6), xytext=(10, -25),
                   textcoords="offset points", fontsize=10, color=NAVY)
    right.set_title("Contribution peaks at the same cutoff", fontsize=13, pad=14)
    right.set_xlabel("Approval cutoff (Synthetic Risk Score)")
    right.set_ylabel("Estimated lifetime net contribution")
    right.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.0f}M"))
    right.set_ylim(0, s.est_net_contribution.max()/1e6*1.16)
    for ax in [left, right]:
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color(GRID)
        ax.grid(axis="y", color=GRID)
        ax.grid(axis="x", visible=False)
        ax.set_xticks(s.threshold.iloc[::2])
        ax.tick_params(labelsize=9)
    fig.text(.055, .103, f"{h['n_applicants']:,} synthetic applications  |  {h['n_scenarios']} cutoffs  |  Python + SQL + Excel",
             fontsize=11, color=NAVY)
    econ = config["economics"]
    fig.text(.055, .064, f"Illustrative economics: {econ['net_margin_on_good_loans']:.0%} lifetime margin on repaid principal; "
             f"{econ['loss_given_default']:.0%} loss on defaulted principal.",
             fontsize=9, color=MUTED)
    fig.text(.055, .034, "Synthetic educational results. No real-world lending validation.", fontsize=9, color=MUTED)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / "portfolio_dashboard.png", out_dir / "portfolio_dashboard.svg"]
    for path in paths:
        fig.savefig(path, dpi=180, bbox_inches=None, metadata={"Date": None} if path.suffix == ".svg" else None)
    plt.close(fig)
    return paths
