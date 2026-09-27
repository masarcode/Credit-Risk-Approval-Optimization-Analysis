"""One-page executive summary (PDF via reportlab) plus a Markdown twin.

All numbers are pulled from the pipeline outputs; nothing is typed in.
"""
from __future__ import annotations

from pathlib import Path

import reportlab
from reportlab import rl_config
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .excel_report import segment_findings

rl_config.invariant = 1  # no timestamps in the PDF, so reruns produce identical files

NAVY = colors.HexColor("#1F3864")
INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#52514e")
TILE = colors.HexColor("#EEF3FA")
LINE = colors.HexColor("#c9d6ea")


def _register_fonts() -> None:
    """Embed ReportLab's bundled Vera fonts for consistent PDF rendering."""
    font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    fonts = {
        "Vera": "Vera.ttf",
        "Vera-Bold": "VeraBd.ttf",
        "Vera-Italic": "VeraIt.ttf",
        "Vera-BoldItalic": "VeraBI.ttf",
    }
    for name, filename in fonts.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, font_dir / filename))
    pdfmetrics.registerFontFamily(
        "Vera",
        normal="Vera",
        bold="Vera-Bold",
        italic="Vera-Italic",
        boldItalic="Vera-BoldItalic",
    )


_register_fonts()


def _styles():
    base = dict(fontName="Vera", textColor=INK, alignment=TA_LEFT)
    return {
        "title": ParagraphStyle("title", fontName="Vera-Bold", fontSize=16, leading=18, textColor=NAVY),
        "sub": ParagraphStyle("sub", **{**base, "textColor": MUTED}, fontSize=7.6, leading=9.5),
        "h": ParagraphStyle("h", fontName="Vera-Bold", fontSize=9.3, leading=11, textColor=NAVY,
                            spaceBefore=4, spaceAfter=1.5),
        "body": ParagraphStyle("body", **base, fontSize=8.0, leading=10),
        "small": ParagraphStyle("small", **{**base, "textColor": MUTED}, fontSize=6.8, leading=8.2),
        "kpi_label": ParagraphStyle("kl", **{**base, "textColor": MUTED}, fontSize=6.3, leading=7.5),
        "kpi_value": ParagraphStyle("kv", fontName="Vera-Bold", fontSize=11.2, leading=13, textColor=NAVY),
        "kpi_delta": ParagraphStyle("kd", **base, fontSize=6.8, leading=8),
    }


def summary_content(tables: dict, headline: dict, config: dict) -> dict:
    h = headline
    sens = tables["sensitivity"].set_index("risk_appetite")
    econ = config["economics"]
    return {
        "question": (
            "How should a consumer lender adjust its approval cutoff to reduce default exposure while keeping "
            "as much approval volume as possible? We treat this as a trade-off, not a race to zero defaults."
        ),
        "recommendation": (
            f"Raise the approval cutoff on the Synthetic Risk Score from <b>{h['baseline_threshold']}</b> to "
            f"<b>{h['recommended_threshold']}</b> (+{h['points_tightened']} points). Approvals fall "
            f"{-h['pct_change_approvals']:.1%} ({h['baseline_approved']:,} to {h['recommended_approved']:,}) while "
            f"defaults among approved loans fall {-h['pct_change_defaults']:.1%} ({h['baseline_defaults']:,} to "
            f"{h['recommended_defaults']:,}). Each 5-point slice removed on the way to {h['recommended_threshold']} "
            f"defaults at {h['last_cut_slice_default_rate']:.1%} or more, above the {h['break_even_default_rate']:.1%} "
            f"count-based break-even rate. The next slice defaults at "
            f"{h['next_slice_default_rate']:.1%}, below break-even, so the rule stops. "
            f"A separate calculation using loan principal shows estimated portfolio contribution rises "
            f"{h['pct_change_net_contribution']:.1%} and peaks at {h['max_net_contribution_threshold']}."
        ),
        "appetite": (
            f"A more conservative lender (assumed margin {sens.loc['conservative', 'assumed_net_margin']:.0%}, "
            f"break-even {sens.loc['conservative', 'break_even_default_rate']:.1%}) would stop at "
            f"{int(sens.loc['conservative', 'recommended_threshold'])}, giving up "
            f"{-sens.loc['conservative', 'pct_change_approvals']:.0%} of approvals to cut defaults "
            f"{-sens.loc['conservative', 'pct_change_defaults']:.0%}. A growth-focused lender (margin "
            f"{sens.loc['growth', 'assumed_net_margin']:.0%}) would stop at "
            f"{int(sens.loc['growth', 'recommended_threshold'])}. The recommendation depends on the lender's "
            f"economics and risk appetite; there is no single correct cutoff."
        ),
        "method": [
            f"{h['n_applicants']:,} synthetic applications generated with a fixed seed; built-in risk relationships "
            "plus random noise. Cleaning removed duplicates, fixed unit errors and imputed missing values.",
            f"Transparent logistic-regression scorecard (9 factors, no protected characteristics). Holdout AUC "
            f"{h['model']['auc_holdout']:.2f}; predicted and observed default rates within "
            f"{abs(h['model']['holdout_mean_pd'] - h['model']['holdout_default_rate']) * 100:.1f} points.",
            f"{h['n_scenarios']} cutoffs from {h['baseline_threshold']} upward in 5-point steps, computed in Python "
            f"and independently in SQL (SQLite); results reconcile exactly. {h['validation_checks_passed']} of "
            f"{h['validation_checks_total']} validation checks pass.",
            f"Unit economics are illustrative: {econ['net_margin_on_good_loans']:.0%} lifetime margin on loans that "
            f"repay, {econ['loss_given_default']:.0%} of principal lost on defaults.",
        ],
        "findings": segment_findings(tables, headline),
        "limitations": [
            "Synthetic data. Relationships are designed, not estimated from real loan performance.",
            "Outcomes are known for declined applicants too; a real lender sees only approved loans.",
            "Results are sensitive to the assumed margin and loss rate; slices next to the break-even "
            "line differ by only 1 to 2 points of default rate.",
            "Full-sample imputation and cutoff selection limit holdout independence. Count-based rule; dollar contribution checked separately.",
        ],
    }


def _kpi_tiles(h: dict, st: dict) -> Table:
    tiles = [
        ("APPROVAL CUTOFF", f"{h['baseline_threshold']} to {h['recommended_threshold']}",
         f"+{h['points_tightened']} points on the risk score"),
        ("APPROVAL RATE", f"{h['baseline_approval_rate']:.1%} to {h['recommended_approval_rate']:.1%}",
         f"{h['pct_change_approvals']:+.1%} approved applicants"),
        ("DEFAULTS (APPROVED LOANS)", f"{h['baseline_defaults']:,} to {h['recommended_defaults']:,}",
         f"{h['pct_change_defaults']:+.1%} defaults"),
        ("DEFAULT RATE (APPROVED)", f"{h['baseline_default_rate']:.1%} to {h['recommended_default_rate']:.1%}",
         f"credit losses {h['pct_change_credit_loss']:+.1%}"),
    ]
    cells = [[Paragraph(a, st["kpi_label"]), Paragraph(b, st["kpi_value"]), Paragraph(c, st["kpi_delta"])]
             for a, b, c in tiles]
    t = Table([[c for c in cells]], colWidths=[1.85 * inch] * 4)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TILE),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 2, colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def build_pdf(content: dict, headline: dict, fig_path: Path, out_path: Path) -> Path:
    st = _styles()
    iw, ih = ImageReader(str(fig_path)).getSize()
    aspect = ih / iw
    img_w = 5.9 * inch
    doc = SimpleDocTemplate(str(out_path), pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch,
                            topMargin=0.45 * inch, bottomMargin=0.4 * inch,
                            title="Credit Risk & Approval Optimization: Executive Summary",
                            author="Synthetic portfolio project")
    flow = [
        Paragraph("Credit Risk &amp; Approval Optimization", st["title"]),
        Paragraph("Executive summary &nbsp;|&nbsp; Synthetic educational analysis of "
                  f"{headline['n_applicants']:,} consumer loan applications. Not for real lending decisions.",
                  st["sub"]),
        Spacer(1, 5),
        Paragraph("<b>Business question.</b> " + content["question"], st["body"]),
        Spacer(1, 6),
        _kpi_tiles(headline, st),
        Paragraph("Recommendation", st["h"]),
        Paragraph(content["recommendation"], st["body"]),
        Spacer(1, 3),
        Image(str(fig_path), width=img_w, height=img_w * aspect),
        Paragraph(content["appetite"], st["small"]),
    ]

    def bullets(items):
        return [Paragraph(f"&bull;&nbsp;{t}", st["small"]) for t in items]

    left = [Paragraph("Where the risk sits", st["h"])] + bullets(content["findings"])
    right = ([Paragraph("How the analysis works", st["h"])] + bullets(content["method"])
             + [Paragraph("Limitations", st["h"])] + bullets(content["limitations"]))
    cols = Table([[left, right]], colWidths=[3.7 * inch, 3.7 * inch])
    cols.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 12)]))
    flow.append(cols)
    doc.build(flow)
    return out_path


def build_markdown(content: dict, headline: dict, out_path: Path) -> Path:
    h = headline
    strip = lambda s: s.replace("<b>", "**").replace("</b>", "**")  # noqa: E731
    lines = [
        "# Credit Risk & Approval Optimization: Executive Summary",
        "",
        f"*Synthetic educational analysis of {h['n_applicants']:,} consumer loan applications. "
        "Not for real lending decisions.*",
        "",
        f"**Business question.** {content['question']}",
        "",
        "| | Baseline | Recommended | Change |",
        "|---|---:|---:|---:|",
        f"| Approval cutoff (Synthetic Risk Score) | {h['baseline_threshold']} | {h['recommended_threshold']} | "
        f"+{h['points_tightened']} points |",
        f"| Applicants approved | {h['baseline_approved']:,} | {h['recommended_approved']:,} | "
        f"{h['pct_change_approvals']:+.1%} |",
        f"| Approval rate | {h['baseline_approval_rate']:.1%} | {h['recommended_approval_rate']:.1%} | "
        f"{(h['recommended_approval_rate'] - h['baseline_approval_rate']) * 100:+.1f} pts |",
        f"| Defaults among approved loans | {h['baseline_defaults']:,} | {h['recommended_defaults']:,} | "
        f"{h['pct_change_defaults']:+.1%} |",
        f"| Default rate of approved loans | {h['baseline_default_rate']:.1%} | {h['recommended_default_rate']:.1%} | "
        f"{(h['recommended_default_rate'] - h['baseline_default_rate']) * 100:+.1f} pts |",
        "",
        "## Recommendation",
        "",
        strip(content["recommendation"]),
        "",
        content["appetite"],
        "",
        "![Marginal slice default rate vs break-even](../figures/03_marginal_slice_vs_break_even.png)",
        "",
        "## Where the risk sits",
        "",
        *[f"- {t}" for t in content["findings"]],
        "",
        "## How the analysis works",
        "",
        *[f"- {t}" for t in content["method"]],
        "",
        "## Limitations",
        "",
        *[f"- {t}" for t in content["limitations"]],
        "",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def build(tables: dict, headline: dict, config: dict, out_dir: Path, fig_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    content = summary_content(tables, headline, config)
    pdf = build_pdf(content, headline, fig_dir / "03_marginal_slice_vs_break_even.png",
                    out_dir / "executive_summary.pdf")
    md = build_markdown(content, headline, out_dir / "executive_summary.md")
    return [pdf, md]
