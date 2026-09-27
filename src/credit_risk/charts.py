"""Static charts for the README and executive summary (matplotlib).

Style rules: one axis per chart (no dual axes), recessive grid, text in
neutral ink, blue for approvals / the score, orange for defaults, the
recommended scenario called out with a label rather than color alone.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter  # noqa: E402

BLUE = "#2a78d6"
ORANGE = "#eb6834"
GRAY = "#b9b8b3"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e6e5e1"
SURFACE = "#ffffff"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 10,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK_2,
    "axes.titlecolor": INK,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "xtick.color": INK_2,
    "ytick.color": INK_2,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
})

pct = PercentFormatter(1.0, decimals=0)


def _titles(fig, title: str, subtitle: str = "", top: float = 0.84) -> None:
    """Left-aligned figure title and subtitle, clear of the plot area."""
    fig.text(0.01, 0.985, title, color=INK, fontsize=13, fontweight="bold", ha="left", va="top")
    if subtitle:
        fig.text(0.01, 0.925, subtitle, color=INK_2, fontsize=9.5, ha="left", va="top")
    fig.subplots_adjust(top=top)


def _save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def tradeoff_curve(scen: pd.DataFrame, rec_t: int, path: Path) -> Path:
    """% of approvals given up vs % of defaults avoided, for each cutoff."""
    x = -scen["pct_change_approvals"]
    y = -scen["pct_change_defaults"]
    fig, ax = plt.subplots(figsize=(7.5, 4.6))
    lim = max(x.max(), y.max()) * 1.08
    xlim = x.max() * 1.18
    ax.plot([0, lim], [0, lim], color=GRAY, lw=1.2, ls=(0, (4, 3)), zorder=1)
    ax.text(xlim * 0.60, xlim * 0.42, "Declining applicants at random\n(no score) would follow this line",
            color=INK_2, fontsize=8, ha="left")
    ax.plot(x, y, color=BLUE, lw=2, zorder=2)
    ax.scatter(x, y, s=42, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=3)
    for _, r in scen.iterrows():
        xi, yi = -r["pct_change_approvals"], -r["pct_change_defaults"]
        if r["threshold"] == rec_t:
            ax.scatter([xi], [yi], s=150, facecolor="none", edgecolor=INK, linewidth=1.6, zorder=4)
            ax.annotate(f"Recommended: {rec_t}\n{xi:.1%} fewer approvals\n{yi:.1%} fewer defaults",
                        (xi, yi), xytext=(28, -38), textcoords="offset points", fontsize=9, color=INK,
                        arrowprops=dict(arrowstyle="-", color=INK_2, lw=0.8))
        elif r["is_baseline"]:
            ax.annotate(f"Baseline {int(r['threshold'])}", (xi, yi), xytext=(10, 2),
                        textcoords="offset points", fontsize=8, color=INK_2, va="bottom")
        elif r["threshold"] in (scen["threshold"].iloc[-1], 580, 590):
            ax.annotate(str(int(r["threshold"])), (xi, yi), xytext=(-8, 7),
                        textcoords="offset points", fontsize=8, color=INK_2)
    ax.set_xlim(-0.01, xlim)
    ax.set_ylim(-0.01, min(1.0, y.max() * 1.1))
    ax.xaxis.set_major_formatter(pct)
    ax.yaxis.set_major_formatter(pct)
    ax.set_xlabel("Approvals given up vs. baseline")
    ax.set_ylabel("Defaults avoided vs. baseline")
    _titles(fig, "Early tightening removes defaults far faster than approvals",
            "Each point is one approval cutoff (Synthetic Risk Score). Returns diminish as the cutoff rises.")
    return _save(fig, path)


def rates_by_threshold(scen: pd.DataFrame, rec_t: int, path: Path) -> Path:
    """Two small multiples (not a dual axis): approval rate and default rate by cutoff."""
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.9))
    specs = [
        (axes[0], "approval_rate", BLUE, "Approval rate", "Share of all applicants approved"),
        (axes[1], "default_rate", ORANGE, "Default rate of approved loans", "Share of approved loans that default"),
    ]
    for ax, col, color, title, ylabel in specs:
        ax.plot(scen["threshold"], scen[col], color=color, lw=2)
        ax.scatter(scen["threshold"], scen[col], s=30, color=color, edgecolor=SURFACE, linewidth=1.5, zorder=3)
        ax.axvline(rec_t, color=INK_2, lw=1, ls=(0, (3, 3)))
        rv = scen.loc[scen["threshold"] == rec_t, col].iloc[0]
        bv = scen[col].iloc[0]
        ax.annotate(f"{bv:.1%}", (scen["threshold"].iloc[0], bv), xytext=(4, 6), textcoords="offset points",
                    fontsize=8.5, color=INK)
        ax.annotate(f"{rv:.1%} at {rec_t}", (rec_t, rv), xytext=(6, 6), textcoords="offset points",
                    fontsize=8.5, color=INK)
        ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.set_xlabel("Approval cutoff (Synthetic Risk Score)")
        ax.set_ylim(0, scen[col].max() * 1.15)
        ax.set_xticks(scen["threshold"][::2])
    fig.tight_layout(rect=(0, 0, 1, 0.84))
    _titles(fig, "Stricter cutoffs trade approval volume for a cleaner book",
            f"Dashed line = recommended cutoff ({rec_t}). Shown as two panels because the measures use different scales.",
            top=0.78)
    return _save(fig, path)


def marginal_slice(scen: pd.DataFrame, rec_t: int, break_even: float, path: Path) -> Path:
    """Default rate of the applicants removed by each 5-point tightening step."""
    s = scen.iloc[1:].copy()
    labels = [f"{int(t) - 5}-{int(t) - 1}" for t in s["threshold"]]
    colors = [BLUE if t <= rec_t else GRAY for t in s["threshold"]]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    bars = ax.bar(labels, s["marginal_default_rate"], color=colors, width=0.72, edgecolor=SURFACE, linewidth=2)
    ax.axhline(break_even, color=ORANGE, lw=1.8)
    ax.text(len(s) - 0.5, break_even + 0.004, f"Break-even default rate {break_even:.1%}",
            color=INK, fontsize=9, ha="right", va="bottom")
    for b, v in zip(bars, s["marginal_default_rate"]):
        y = v + 0.003 if abs(v - break_even) > 0.012 or v > break_even else break_even + 0.005
        ax.text(b.get_x() + b.get_width() / 2, y, f"{v:.1%}", ha="center", fontsize=8, color=INK_2)
    ax.yaxis.set_major_formatter(pct)
    ax.set_ylabel("Default rate of applicants removed")
    ax.set_xlabel("Score range removed by each 5-point tightening step")
    _titles(fig, f"The count-based break-even rule stops at {rec_t}",
            f"Blue: groups removed through {rec_t}. Gray: groups below break-even. "
            "Dollar contribution is checked separately.")
    ax.tick_params(axis="x", labelsize=8.5)
    ax.set_ylim(0, s["marginal_default_rate"].max() * 1.18)
    ax.grid(axis="x", visible=False)
    return _save(fig, path)


def segment_default_rates(seg: pd.DataFrame, path: Path) -> Path:
    dims = ["Credit score", "Debt-to-income"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    for ax, dim in zip(axes, dims):
        d = seg[seg["dimension"] == dim].sort_values("band_order")
        y = np.arange(len(d))
        ax.barh(y - .18, d["share_of_applicants"], color=BLUE, height=.33, label="Share of applicants")
        ax.barh(y + .18, d["share_of_defaults"], color=ORANGE, height=.33, label="Share of defaults")
        ax.set_yticks(y, d["band"])
        ax.invert_yaxis()
        for offset, col in [(-.18, "share_of_applicants"), (.18, "share_of_defaults")]:
            for yi, v in zip(y, d[col]):
                ax.text(v+.006, yi+offset, f"{v:.1%}", va="center", fontsize=8, color=INK_2)
        ax.set_xlim(0, .55)
        ax.xaxis.set_major_formatter(pct)
        ax.set_title(dim, fontsize=11)
        ax.set_xlabel("Share of synthetic portfolio total")
        ax.grid(axis="y", visible=False)
    axes[0].legend(frameon=False, loc="lower right", fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, .80), w_pad=3)
    _titles(fig, "Defaults concentrate in weaker credit and higher debt-to-income bands",
            "Compare each band's share of applicants with its share of all defaults. Each dimension sums to 100%.", top=.76)
    return _save(fig, path)


def risk_heatmap(matrix: pd.DataFrame, path: Path) -> Path:
    piv = matrix.pivot_table(index=["credit_score_band_order", "credit_score_band"],
                             columns=["dti_band_order", "dti_band"], values="default_rate")
    cnt = matrix.pivot_table(index=["credit_score_band_order", "credit_score_band"],
                             columns=["dti_band_order", "dti_band"], values="applicants")
    rows = [r[1] for r in piv.index]
    cols = [c[1] for c in piv.columns]
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", SEQ)
    fig, ax = plt.subplots(figsize=(8, 4.8))
    im = ax.imshow(piv.values, cmap=cmap, vmin=0, vmax=0.7, aspect="auto")
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v, n = piv.values[i, j], cnt.values[i, j]
            if np.isnan(v):
                continue
            color = "white" if v > 0.3 else INK
            txt = f"{v:.0%}" if n >= 100 else f"{v:.0%}*"
            ax.text(j, i - 0.12, txt, ha="center", va="center", fontsize=10, color=color, fontweight="bold")
            ax.text(j, i + 0.22, f"n={int(n):,}", ha="center", va="center", fontsize=7, color=color)
    ax.set_xticks(range(len(cols)), cols)
    ax.set_yticks(range(len(rows)), rows)
    ax.set_xlabel("Debt-to-income ratio")
    ax.set_ylabel("Credit score band")
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02, format=pct)
    cb.outline.set_visible(False)
    cb.set_label("Default rate", color=INK_2)
    _titles(fig, "Risk compounds when weak credit and high debt load overlap",
            "Default rate by credit score band and DTI band. * = fewer than 100 applicants.", top=0.83)
    return _save(fig, path)


def net_contribution(scen: pd.DataFrame, rec_t: int, margin: float, lgd: float, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    vals = scen["est_net_contribution"] / 1e6
    colors = [BLUE if t == rec_t else "#86b6ef" for t in scen["threshold"]]
    bars = ax.bar(scen["threshold"].astype(str), vals, color=colors, width=0.72, edgecolor=SURFACE, linewidth=2)
    for b, v, t in zip(bars, vals, scen["threshold"]):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.6, f"${v:.1f}M", ha="center", fontsize=8,
                color=INK if t == rec_t else INK_2, fontweight="bold" if t == rec_t else "normal")
    ax.set_ylim(0, vals.max() * 1.12)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:.0f}M"))
    ax.set_xlabel("Approval cutoff (Synthetic Risk Score)")
    ax.set_ylabel("Estimated net contribution")
    ax.grid(axis="x", visible=False)
    peak = int(scen.loc[scen["est_net_contribution"].idxmax(), "threshold"])
    _titles(fig, f"Estimated portfolio contribution peaks at a cutoff of {peak}",
            f"Illustrative unit economics: {margin:.0%} lifetime margin on loans that repay, "
            f"{lgd:.0%} of principal lost on loans that default.")
    return _save(fig, path)


def calibration(cal: pd.DataFrame, auc_holdout: float, path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(7, 4.2))
    x = np.arange(len(cal))
    w = 0.38
    ax.bar(x - w / 2 - 0.01, cal["mean_predicted_pd"], width=w, color=BLUE, label="Predicted by score")
    ax.bar(x + w / 2 + 0.01, cal["observed_default_rate"], width=w, color=ORANGE, label="Observed")
    ax.set_xticks(x, [str(d) for d in cal["risk_decile"]])
    ax.set_xlabel("Risk decile on the holdout sample (1 = safest, 10 = riskiest)")
    ax.set_ylabel("Default rate")
    ax.yaxis.set_major_formatter(pct)
    ax.legend(frameon=False, loc="upper left")
    ax.grid(axis="x", visible=False)
    _titles(fig, "Predicted and observed risk track closely across holdout deciles",
            f"Model fitted on development sample. AUC = {auc_holdout:.3f}; preprocessing used full-sample medians.")
    return _save(fig, path)


def build_all(tables: dict, headline: dict, config: dict, fig_dir: Path) -> list[Path]:
    scen = tables["scenarios"]
    rec_t = headline["recommended_threshold"]
    econ = config["economics"]
    return [
        tradeoff_curve(scen, rec_t, fig_dir / "01_tradeoff_curve.png"),
        marginal_slice(scen, rec_t, headline["break_even_default_rate"], fig_dir / "03_marginal_slice_vs_break_even.png"),
        segment_default_rates(tables["segments"], fig_dir / "04_default_rate_by_segment.png"),
        risk_heatmap(tables["matrix"], fig_dir / "05_credit_score_by_dti_heatmap.png"),
        calibration(tables["calibration"], headline["model"]["auc_holdout"], fig_dir / "07_holdout_calibration.png"),
    ]
