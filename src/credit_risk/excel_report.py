"""Decision-support Excel workbook.

The workbook is a working tool, not a static export:

* Assumptions (baseline cutoff, margin, loss given default) are input cells.
* Scenario metrics that depend on those assumptions are live formulas, so a
  reader can change the margin and watch the break-even rate, the losses
  and the recommended cutoff update.
* Counts that come from the 100,000 applicant records (approvals, defaults,
  loan volumes) are pasted as values from the Python/SQL pipeline, because
  the raw data does not live in the workbook.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .data_dictionary import EXCLUDED_BY_DESIGN, as_frame

FONT = "Arial"
NAVY = "1F3864"
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
BAND_FILL = PatternFill("solid", fgColor="EEF3FA")
REC_FILL = PatternFill("solid", fgColor="DDEBF7")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

PCT = "0.0%"
PCT_SIGNED = "+0.0%;-0.0%;0.0%"
INT = "#,##0"
INT_SIGNED = "+#,##0;-#,##0;0"
USD = "$#,##0"
DEC1 = "#,##0.0"

SC = "'Scenario Analysis'"
ES = "'Executive Summary'"


def _f(bold=False, size=10, color="000000", italic=False):
    return Font(name=FONT, bold=bold, size=size, color=color, italic=italic)


def _header_row(ws, row: int, headers: list[str], start_col: int = 1, height: float = 32) -> None:
    for j, h in enumerate(headers):
        c = ws.cell(row=row, column=start_col + j, value=h)
        c.font = _f(bold=True, color="FFFFFF")
        c.fill = HEADER_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BOX
    ws.row_dimensions[row].height = height


def _title(ws, text: str, sub: str) -> None:
    ws["A1"] = text
    ws["A1"].font = _f(bold=True, size=15, color=NAVY)
    ws["A2"] = sub
    ws["A2"].font = _f(italic=True, color="595959")


def _section(ws, cell: str, text: str) -> None:
    ws[cell] = text
    ws[cell].font = _f(bold=True, size=11, color=NAVY)


# ---------------------------------------------------------------------------
# Scenario Analysis
# ---------------------------------------------------------------------------
SCEN_COLS = [
    # (header, width, kind, source/formula template, number format)
    ("Scenario ID", 9, "value", "scenario_id", None),
    ("Scenario", 15, "value", "scenario_label", None),
    ("Approval cutoff (SRS)", 10, "value", "threshold", "0"),
    ("Applicants approved", 11, "value", "approved", INT),
    ("Applicants declined", 11, "formula", "={total}-D{r}", INT),
    ("Approval rate", 9, "formula", "=D{r}/{total}", PCT),
    ("Approved defaults", 10, "value", "approved_defaults", INT),
    ("Default rate (approved)", 10, "formula", "=G{r}/D{r}", PCT),
    ("Expected defaults (score)", 11, "value", "expected_defaults", DEC1),
    ("Approved loan volume ($)", 15, "value", "approved_loan_volume", USD),
    ("Defaulted loan volume ($)", 14, "value", "defaulted_loan_volume", USD),
    ("Est. credit loss ($)", 14, "formula", "=K{r}*{lgd}", USD),
    ("Est. net contribution ($)", 15, "formula", "=(J{r}-K{r})*{margin}-K{r}*{lgd}", USD),
    ("Avg credit score (approved)", 10, "value", "avg_credit_score", DEC1),
    ("Avg annual income (approved)", 12, "value", "avg_annual_income", USD),
    ("Avg DTI (approved)", 9, "value", "avg_dti", PCT),
    ("Change in approvals vs baseline", 12, "formula", "=D{r}-INDEX($D${r0}:$D${r1},MATCH({base},$C${r0}:$C${r1},0))", INT_SIGNED),
    ("% change in approvals", 10, "formula", "=Q{r}/INDEX($D${r0}:$D${r1},MATCH({base},$C${r0}:$C${r1},0))", PCT_SIGNED),
    ("Change in defaults vs baseline", 11, "formula", "=G{r}-INDEX($G${r0}:$G${r1},MATCH({base},$C${r0}:$C${r1},0))", INT_SIGNED),
    ("% change in defaults", 10, "formula", "=S{r}/INDEX($G${r0}:$G${r1},MATCH({base},$C${r0}:$C${r1},0))", PCT_SIGNED),
    ("Defaults avoided per 100 approvals lost", 12, "formula", '=IF(Q{r}<0,100*S{r}/Q{r},"")', DEC1),
    ("Slice declined (vs previous cutoff)", 11, "formula", '=IF(ROW()={r0},"",D{rp}-D{r})', INT),
    ("Slice defaults avoided", 10, "formula", '=IF(ROW()={r0},"",G{rp}-G{r})', INT),
    ("Slice default rate", 10, "formula", '=IF(ROW()={r0},"",W{r}/V{r})', PCT),
    ("Slice above break-even?", 10, "formula", '=IF(ROW()={r0},"",IF(X{r}>={be},"Yes","No"))', None),
    ("Keep tightening? (rule)", 11, "formula", None, None),  # built separately
]


def _scenario_sheet(wb: Workbook, scen: pd.DataFrame) -> dict:
    ws = wb.create_sheet("Scenario Analysis")
    _title(ws, "Scenario Analysis: 12 approval cutoffs",
           "Blue cells are values from the Python/SQL pipeline. Black cells are formulas that respond to the "
           "inputs on the Executive Summary sheet.")
    hr, r0 = 4, 5
    r1 = r0 + len(scen) - 1
    refs = {"total": f"{ES}!$C$9", "lgd": f"{ES}!$C$7", "margin": f"{ES}!$C$6",
            "base": f"{ES}!$C$5", "be": f"{ES}!$C$8", "r0": r0, "r1": r1}
    _header_row(ws, hr, [c[0] for c in SCEN_COLS], height=58)
    for i, (_, row) in enumerate(scen.iterrows()):
        r = r0 + i
        for j, (header, width, kind, src, fmt) in enumerate(SCEN_COLS, start=1):
            cell = ws.cell(row=r, column=j)
            if kind == "value":
                v = row[src]
                cell.value = v.item() if hasattr(v, "item") else v
                cell.font = _f(color="0000FF")
            elif src is not None:
                cell.value = src.format(r=r, rp=r - 1, **refs)
                cell.font = _f()
            if fmt:
                cell.number_format = fmt
            cell.border = BOX
            cell.alignment = Alignment(horizontal="center" if j <= 3 else "right")
        # Keep tightening flag: TRUE from the baseline row while every slice so far is above break-even
        z = ws.cell(row=r, column=26)
        if i == 0:
            z.value = f"=C{r}={refs['base']}"
        else:
            z.value = f"=IF(C{r}<{refs['base']},FALSE,IF(C{r}={refs['base']},TRUE,AND(Z{r - 1},X{r}>={refs['be']})))"
        z.font = _f()
        z.border = BOX
        z.alignment = Alignment(horizontal="center")
    for j, c in enumerate(SCEN_COLS, start=1):
        ws.column_dimensions[get_column_letter(j)].width = c[1]
    ws.freeze_panes = ws.cell(row=r0, column=4)

    note_r = r1 + 2
    notes = [
        "How to read this sheet",
        "Approval rule: approve an applicant when their Synthetic Risk Score (SRS) is at or above the cutoff.",
        "Slice = the applicants removed when the cutoff moves up 5 points from the previous row.",
        "Keep tightening? = TRUE while every slice removed so far defaults at or above the break-even rate. "
        "The recommended cutoff is the highest cutoff still marked TRUE.",
        "Estimated net contribution = (approved volume - defaulted volume) x margin - defaulted volume x loss given "
        "default. Illustrative unit economics only.",
        "Expected defaults (score) = sum of each approved applicant's predicted probability of default; it should "
        "track the observed defaults closely if the score is well calibrated.",
    ]
    for k, text in enumerate(notes):
        c = ws.cell(row=note_r + k, column=1, value=text)
        c.font = _f(bold=(k == 0), italic=(k > 0), color="404040")
    return {"r0": r0, "r1": r1}


# ---------------------------------------------------------------------------
# Executive Summary
# ---------------------------------------------------------------------------
def _summary_sheet(wb: Workbook, headline: dict, config: dict, rows: dict, tables: dict) -> None:
    ws = wb.active
    ws.title = "Executive Summary"
    r0, r1 = rows["r0"], rows["r1"]
    econ = config["economics"]
    _title(ws, "Credit Risk & Approval Optimization: Decision Summary",
           f"Synthetic educational dataset of {headline['n_applicants']:,} applicants. "
           "Not a real lending system and not for real credit decisions.")

    _section(ws, "B4", "Decision inputs (yellow cells can be changed)")
    inputs = [
        (5, "Baseline approval cutoff (current policy)", config["scenarios"]["baseline_threshold"], "0",
         "Must be one of the 12 cutoffs on the Scenario Analysis sheet."),
        (6, "Net margin on loans that repay (lifetime)", econ["net_margin_on_good_loans"], PCT,
         "Illustrative assumption: interest earned minus funding and servicing cost, as a share of principal."),
        (7, "Loss given default (share of principal lost)", econ["loss_given_default"], PCT,
         "Illustrative assumption for an unsecured personal loan."),
    ]
    for r, label, val, fmt, note in inputs:
        ws.cell(row=r, column=2, value=label).font = _f()
        c = ws.cell(row=r, column=3, value=val)
        c.font = _f(color="0000FF", bold=True)
        c.fill = INPUT_FILL
        c.number_format = fmt
        c.border = BOX
        c.comment = Comment(note, "Pipeline")
    ws["B8"] = "Break-even default rate = margin / (margin + loss given default)"
    ws["B8"].font = _f()
    ws["C8"] = "=C6/(C6+C7)"
    ws["C8"].number_format = PCT
    ws["C8"].font = _f(bold=True)
    ws["C8"].border = BOX
    ws["B9"] = "Total applicants in dataset"
    ws["B9"].font = _f()
    ws["C9"] = headline["n_applicants"]
    ws["C9"].number_format = INT
    ws["C9"].font = _f(color="0000FF")
    ws["C9"].border = BOX

    dv = DataValidation(type="list", formula1=f"={SC}!$C${r0}:$C${r1}", allow_blank=False)
    ws.add_data_validation(dv)
    dv.add("C5")
    dv.showErrorMessage = True
    dv.errorTitle = "Choose a tested cutoff"
    dv.error = "Choose a cutoff from the dropdown."
    for cell, low, label in [("C6", 0, "Margin"), ("C7", 0.000001, "Loss given default")]:
        check = DataValidation(type="decimal", operator="between", formula1=low,
                               formula2=1, allow_blank=False)
        check.showErrorMessage = True
        check.errorTitle = "Check the assumption"
        check.error = f"{label} must be between {low:.6f} and 1 (100%)."
        ws.add_data_validation(check)
        check.add(cell)

    _section(ws, "B11", "Recommendation")
    ws["B12"] = "Recommended approval cutoff (marginal break-even rule)"
    ws["B12"].font = _f(bold=True)
    ws["C12"] = f"=SUMPRODUCT(MAX(({SC}!$Z${r0}:$Z${r1}=TRUE)*{SC}!$C${r0}:$C${r1}))"
    ws["C12"].font = _f(bold=True, size=12, color=NAVY)
    ws["C12"].fill = REC_FILL
    ws["C12"].border = BOX
    ws["C12"].number_format = "0"

    _header_row(ws, 14, ["Metric", "Baseline", "Recommended", "Change", "% change"], start_col=2, height=22)
    metrics = [
        ("Approval cutoff (SRS)", "C", "0", False),
        ("Applicants approved", "D", INT, True),
        ("Approval rate", "F", PCT, False),
        ("Approved defaults", "G", INT, True),
        ("Default rate (approved loans)", "H", PCT, False),
        ("Estimated credit loss ($)", "L", USD, True),
        ("Estimated net contribution ($)", "M", USD, True),
    ]
    for k, (label, col, fmt, pct_change) in enumerate(metrics):
        r = 15 + k
        rng, key = f"{SC}!${col}${r0}:${col}${r1}", f"{SC}!$C${r0}:$C${r1}"
        ws.cell(row=r, column=2, value=label).font = _f()
        ws.cell(row=r, column=3, value=f"=INDEX({rng},MATCH($C$5,{key},0))")
        ws.cell(row=r, column=4, value=f"=INDEX({rng},MATCH($C$12,{key},0))")
        ws.cell(row=r, column=5, value=f"=D{r}-C{r}")
        ws.cell(row=r, column=6, value=f"=IF(C{r}=0,\"\",D{r}/C{r}-1)" if pct_change else "")
        for col_i in range(2, 7):
            c = ws.cell(row=r, column=col_i)
            c.border = BOX
            if col_i >= 3:
                c.font = _f()
                c.number_format = fmt if col_i in (3, 4) else (
                    {"0": "+0;-0;0", INT: INT_SIGNED, USD: "+$#,##0;-$#,##0;$0", PCT: "+0.0%;-0.0%;0.0%"}[fmt]
                    if col_i == 5 else PCT_SIGNED)
        if label.startswith("Approval rate") or label.startswith("Default rate"):
            ws.cell(row=r, column=5).number_format = '+0.0" pts";-0.0" pts";0.0" pts"'
            ws.cell(row=r, column=5).value = f"=(D{r}-C{r})*100"

    ws["B23"] = "Key recommendation"
    ws["B23"].font = _f(bold=True, size=11, color=NAVY)
    ws["B24"] = ('=IF(C12=C5,"Keep the approval cutoff at "&C5,"Raise the approval cutoff from "&C5&" to "&C12)&". Approvals fall by "&TEXT(-F16,"0.0%")'
                 '&" while defaults fall by "&TEXT(-F18,"0.0%")&", cutting the default rate on approved loans from "'
                 '&TEXT(C19,"0.0%")&" to "&TEXT(D19,"0.0%")&"."')
    ws["B25"] = (f'=IF(C12=MAX({SC}!$C${r0}:$C${r1}),'
                 '"The rule reaches the highest tested cutoff. No higher cutoff is evaluated.",'
                 'IF(C12=C5,"The next slice falls below the count-based break-even rate. The rule keeps the baseline.",'
                 '"Each removed slice meets the count-based break-even rate; the next slice falls below it. "'
                 '&"Dollar contribution is calculated separately."))')
    for cell in ("B24", "B25"):
        ws[cell].font = _f()
        ws[cell].alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(f"{cell}:F{cell[1:]}")
        ws.row_dimensions[int(cell[1:])].height = 44

    _section(ws, "B27", "Major segment findings (from SQL segmentation; base-case assumptions)")
    for k, text in enumerate(segment_findings(tables, headline)):
        c = ws.cell(row=28 + k, column=2, value=f"{k + 1}. {text}")
        c.font = _f()
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=28 + k, start_column=2, end_row=28 + k, end_column=6)
        ws.row_dimensions[28 + k].height = 32

    sr = 28 + len(segment_findings(tables, headline)) + 1
    _section(ws, f"B{sr}", "Different risk appetites (values from the pipeline)")
    _header_row(ws, sr + 1, ["Risk appetite", "Assumed margin", "Break-even default rate", "Cutoff",
                             "Approvals vs baseline", "Defaults vs baseline"], start_col=2, height=30)
    for k, row in tables["sensitivity"].iterrows():
        r = sr + 2 + k
        vals = [row["risk_appetite"].title(), row["assumed_net_margin"], row["break_even_default_rate"],
                int(row["recommended_threshold"]), row["pct_change_approvals"], row["pct_change_defaults"]]
        fmts = [None, PCT, PCT, "0", PCT_SIGNED, PCT_SIGNED]
        for j, (v, fmt) in enumerate(zip(vals, fmts)):
            c = ws.cell(row=r, column=2 + j, value=v.item() if hasattr(v, "item") else v)
            c.font = _f(color="0000FF" if j else "000000")
            c.border = BOX
            if fmt:
                c.number_format = fmt

    lr = sr + 2 + len(tables["sensitivity"]) + 1
    _section(ws, f"B{lr}", "Limitations")
    lims = [
        "Synthetic data: relationships were designed to be realistic but are not estimated from real loans.",
        "Outcomes are known for every applicant, including declined ones. Real lenders only observe approved loans.",
        "Margin and loss-given-default are illustrative. Change the yellow cells to test other assumptions.",
        "Adjacent slices near the break-even line differ by about 1 to 2 points of default rate, so cutoffs one "
        "step either side are also defensible.",
        "Imputation and cutoff selection use the full cohort. Policy results are not an independent holdout test.",
    ]
    for k, t in enumerate(lims):
        c = ws.cell(row=lr + 1 + k, column=2, value=f"- {t}")
        c.font = _f(italic=True, color="404040")
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=lr + 1 + k, start_column=2, end_row=lr + 1 + k, end_column=7)
        ws.row_dimensions[lr + 1 + k].height = 28

    ws.column_dimensions["A"].width = 2
    ws.column_dimensions["B"].width = 58
    for col in "CDEFG":
        ws.column_dimensions[col].width = 17


def segment_findings(tables: dict, headline: dict) -> list[str]:
    """Plain-English segment findings computed from the SQL outputs (no hard-coded numbers)."""
    seg, tight, matrix = tables["segments"], tables["tightening"], tables["matrix"]
    cs = seg[seg["dimension"] == "Credit score"].set_index("band")
    low = cs.loc[["<580", "580-619"]]
    top5 = matrix.nsmallest(5, "cumulative_share_of_defaults")
    ct = tight[tight["dimension"] == "Credit score"].set_index("band")
    mid_share = ct.loc[["580-619", "620-659"], "share_of_all_approvals_lost"].sum()
    top_share = ct.loc[["700-739", "740+"], "share_of_all_approvals_lost"].sum()
    dti = seg[seg["dimension"] == "Debt-to-income"].set_index("band")
    loan = seg[seg["dimension"] == "Loan size"]
    return [
        f"Applicants with credit scores below 620 are {low['share_of_applicants'].sum():.0%} of applicants but "
        f"{low['share_of_defaults'].sum():.0%} of all defaults.",
        f"Five credit-score x DTI combinations hold {top5['share_of_applicants'].sum():.0%} of applicants and "
        f"{top5['share_of_defaults'].sum():.0%} of defaults"
        + ("; all combine a sub-660 score with DTI of 20% or more."
           if ((top5["credit_score_band_order"] <= 3) & (top5["dti_band_order"] >= 3)).all() else "."),
        f"Default rates climb from {dti.loc['<10%', 'default_rate']:.1%} for DTI under 10% to "
        f"{dti.loc['40%+', 'default_rate']:.1%} for DTI of 40% or more.",
        f"Moving to the recommended cutoff mainly affects the 580-659 score bands ({mid_share:.0%} of approvals "
        f"given up); applicants scoring 700+ are almost untouched ({top_share:.1%}).",
        f"Loan size alone barely separates risk (default rates of {loan['default_rate'].min():.1%} to "
        f"{loan['default_rate'].max():.1%} across size bands); what matters is loan size relative to income.",
    ]


# ---------------------------------------------------------------------------
# Segment Risk, Score Drivers, Data Dictionary
# ---------------------------------------------------------------------------
def _segment_sheet(wb: Workbook, tables: dict, headline: dict) -> None:
    ws = wb.create_sheet("Segment Risk")
    _title(ws, "Segment Risk: where defaults concentrate",
           f"All values generated by sql/risk_segments.sql against the SQLite database. Baseline cutoff "
           f"{headline['baseline_threshold']}, recommended cutoff {headline['recommended_threshold']}.")
    seg = tables["segments"].merge(
        tables["tightening"][["dimension", "band", "approvals_lost", "pct_of_band_approvals_lost"]],
        on=["dimension", "band"])
    order = ["Credit score", "Debt-to-income", "Card utilization", "Recent delinquencies", "Income", "Loan size"]
    seg["dim_order"] = seg["dimension"].map({d: i for i, d in enumerate(order)})
    seg = seg.sort_values(["dim_order", "band_order"])

    _section(ws, "A4", "1. Default rate and default concentration by segment")
    headers = ["Dimension", "Segment", "Applicants", "Defaults", "Default rate", "Share of applicants",
               "Share of defaults", "Approval rate at baseline", "Approval rate at recommended",
               "Approvals lost", "% of segment's approvals lost"]
    _header_row(ws, 5, headers, height=44)
    r = 6
    first = r
    prev = None
    for _, row in seg.iterrows():
        vals = [row["dimension"] if row["dimension"] != prev else "", row["band"], row["applicants"],
                row["defaults"], row["default_rate"], row["share_of_applicants"], row["share_of_defaults"],
                row["baseline_approval_rate"], row["recommended_approval_rate"], row["approvals_lost"],
                row["pct_of_band_approvals_lost"]]
        fmts = [None, None, INT, INT, PCT, PCT, PCT, PCT, PCT, INT, PCT]
        for j, (v, fmt) in enumerate(zip(vals, fmts), start=1):
            c = ws.cell(row=r, column=j, value=v.item() if hasattr(v, "item") else v)
            c.font = _f(bold=(j == 1))
            c.border = BOX
            if fmt:
                c.number_format = fmt
            if row["dimension"] in ("Credit score", "Card utilization", "Income"):
                c.fill = BAND_FILL
        prev = row["dimension"]
        r += 1
    ws.conditional_formatting.add(f"E{first}:E{r - 1}", ColorScaleRule(
        start_type="num", start_value=0, start_color="FFFFFF", end_type="num", end_value=0.6, end_color="F4B183"))

    r += 1
    _section(ws, f"A{r}", "2. Highest-risk borrower profiles (score x DTI x utilization, 300+ applicants)")
    r += 1
    _header_row(ws, r, ["Credit score", "DTI", "Utilization", "Applicants", "Defaults", "Default rate",
                        "Approval rate at baseline", "Approval rate at recommended"], height=44)
    r += 1
    for _, row in tables["profiles"].iterrows():
        vals = [row["credit_score_band"], row["dti_band"], row["utilization_band"], row["applicants"],
                row["defaults"], row["default_rate"], row["baseline_approval_rate"], row["recommended_approval_rate"]]
        fmts = [None, None, None, INT, INT, PCT, PCT, PCT]
        for j, (v, fmt) in enumerate(zip(vals, fmts), start=1):
            c = ws.cell(row=r, column=j, value=v.item() if hasattr(v, "item") else v)
            c.font = _f()
            c.border = BOX
            if fmt:
                c.number_format = fmt
        r += 1

    r += 1
    _section(ws, f"A{r}", "3. Where defaults are concentrated (credit score x DTI, ranked by number of defaults)")
    r += 1
    _header_row(ws, r, ["Credit score", "DTI", "Applicants", "Defaults", "Default rate", "Share of applicants",
                        "Share of defaults", "Cumulative share of defaults"], height=44)
    r += 1
    for _, row in tables["matrix"].head(10).iterrows():
        vals = [row["credit_score_band"], row["dti_band"], row["applicants"], row["defaults"],
                row["default_rate"], row["share_of_applicants"], row["share_of_defaults"],
                row["cumulative_share_of_defaults"]]
        fmts = [None, None, INT, INT, PCT, PCT, PCT, PCT]
        for j, (v, fmt) in enumerate(zip(vals, fmts), start=1):
            c = ws.cell(row=r, column=j, value=v.item() if hasattr(v, "item") else v)
            c.font = _f()
            c.border = BOX
            if fmt:
                c.number_format = fmt
        r += 1

    widths = [20, 13, 12, 11, 11, 12, 12, 13, 13, 11, 13]
    for j, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A6"


def _drivers_sheet(wb: Workbook, tables: dict, headline: dict) -> None:
    ws = wb.create_sheet("Score Drivers")
    m = headline["model"]
    _title(ws, "What moves the Synthetic Risk Score (SRS)",
           "Logistic regression fitted on a 70% development sample and tested on a 30% holdout. "
           "Higher score = lower risk. 600 points = 20-to-1 odds of repaying; +20 points doubles the odds.")
    _header_row(ws, 4, ["Factor", "Example change", "Score points", "Odds of default multiplied by", "p-value"],
                height=32)
    d = tables["drivers"].copy()
    d["abs"] = d["score_point_impact"].abs()
    for k, (_, row) in enumerate(d.sort_values("abs", ascending=False).iterrows()):
        r = 5 + k
        vals = [row["feature"], row["example_change"], row["score_point_impact"],
                row["odds_of_default_multiplier"], row["p_value"]]
        fmts = [None, None, "+0.0;-0.0", "0.00x", "0.0E+00"]
        for j, (v, fmt) in enumerate(zip(vals, fmts), start=1):
            c = ws.cell(row=r, column=j, value=v.item() if hasattr(v, "item") else v)
            c.font = _f()
            c.border = BOX
            if fmt:
                c.number_format = fmt
    r = 6 + len(d)
    _section(ws, f"A{r}", "Model quality (holdout excluded from coefficient fitting)")
    stats = [
        ("Development / holdout applicants", f"{m['n_development']:,} / {m['n_holdout']:,}"),
        ("AUC (holdout)", round(m["auc_holdout"], 3)),
        ("AUC (development)", round(m["auc_development"], 3)),
        ("Gini (holdout)", round(m["gini_holdout"], 3)),
        ("KS statistic (holdout)", round(m["ks_holdout"], 3)),
        ("Predicted vs observed default rate (holdout)",
         f"{m['holdout_mean_pd']:.2%} vs {m['holdout_default_rate']:.2%}"),
    ]
    for k, (label, v) in enumerate(stats):
        ws.cell(row=r + 1 + k, column=1, value=label).font = _f()
        c = ws.cell(row=r + 1 + k, column=2, value=v)
        c.font = _f(color="0000FF")
        c.border = BOX
    r = r + len(stats) + 2
    _section(ws, f"A{r}", "Features tested but not kept (not statistically clear or wrong direction)")
    dropped = tables["screening"][~tables["screening"]["retained"]]
    for k, (_, row) in enumerate(dropped.iterrows()):
        ws.cell(row=r + 1 + k, column=1, value=row["feature"]).font = _f()
        ws.cell(row=r + 1 + k, column=2,
                value=f"{row['reason']} (p = {row['p_value']:.2f})").font = _f(italic=True, color="404040")
    for col, w in zip("ABCDE", [44, 36, 13, 16, 12]):
        ws.column_dimensions[col].width = w


def _dictionary_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("Data Dictionary")
    _title(ws, "Data Dictionary", "Every field in the applicant-level dataset. " + EXCLUDED_BY_DESIGN)
    df = as_frame()
    _header_row(ws, 4, list(df.columns), height=22)
    for i, row in enumerate(df.itertuples(index=False), start=5):
        ws.row_dimensions[i].height = 30
        for j, v in enumerate(row, start=1):
            c = ws.cell(row=i, column=j, value=v)
            c.font = _f(bold=(j == 1))
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.border = BOX
    for col, w in zip("ABCDE", [32, 60, 11, 26, 40]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A5"


def build_workbook(tables: dict, headline: dict, config: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    rows = _scenario_sheet(wb, tables["scenarios"])
    _summary_sheet(wb, headline, config, rows, tables)
    _segment_sheet(wb, tables, headline)
    _drivers_sheet(wb, tables, headline)
    _dictionary_sheet(wb)
    wb.move_sheet("Executive Summary", offset=-wb.index(wb["Executive Summary"]))
    wb.active = 0
    for ws in wb.worksheets:  # print-friendly: landscape, one page wide
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.sheet_view.showGridLines = False
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
    return path
