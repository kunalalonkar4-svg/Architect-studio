"""Professional BOQ workbook (openpyxl): abstract of cost, item-wise BOQ with live formulas, preliminary structure sheet, notes."""
from __future__ import annotations

import io
import datetime as dt

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .estimate import DEFAULT_RATES, estimate
from .model import ProjectModel
from .structural import prelim

GROUPS = [
    ("A", "EARTHWORK AND FOUNDATION", ["excavation", "pcc", "foundation"]),
    ("B", "RCC STRUCTURE", ["slab", "steel"]),
    ("C", "MASONRY AND PLASTERING", ["masonry", "plaster"]),
    ("D", "FLOORING, DOORS, WINDOWS AND PAINTING", ["flooring", "doors", "windows", "paint"]),
    ("E", "WATERPROOFING AND SERVICES", ["waterproof", "electrical", "plumbing", "sanitary"]),
]
THIN = Side(style="thin", color="999999")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD = PatternFill("solid", fgColor="1F3A5F")
BAND = PatternFill("solid", fgColor="E8EEF5")


def _hdr(ws, row, labels, widths=None):
    for i, t in enumerate(labels, 1):
        c = ws.cell(row=row, column=i, value=t)
        c.font = Font(bold=True, color="FFFFFF"); c.fill = HEAD; c.border = BOX
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def build_boq_xlsx(model: ProjectModel, project_name: str, revision: int, rates: dict | None = None, contingency_pct: float = 5.0,
                   client: str = "", address: str = "") -> bytes:
    est = estimate(model)
    rt = {**DEFAULT_RATES, **{k: float(v) for k, v in (rates or {}).items() if k in DEFAULT_RATES}}
    items = {i["id"]: i for i in est["items"]}
    wb = Workbook()
    # ---------------- BOQ
    ws = wb.active; ws.title = "BOQ"
    ws["A1"] = "BILL OF QUANTITIES (PRELIMINARY)"; ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Project: {project_name}"; ws["A3"] = f"Client / site: {client or '-'}   Address: {address or '-'}"
    ws["A4"] = f"Drawing revision: {revision}   Date: {dt.date.today().isoformat()}   Floors: {est.get('floors', 1)}   Built-up area: {est['built_up_m2']} m2"
    _hdr(ws, 6, ["Sr.", "Description of item", "Unit", "Quantity", "Rate (INR)", "Amount (INR)", "Basis of quantity"])
    r = 7
    group_rows: list[tuple[str, str, int]] = []
    for code, title, ids in GROUPS:
        ws.cell(row=r, column=1, value=code).font = Font(bold=True)
        c = ws.cell(row=r, column=2, value=title); c.font = Font(bold=True)
        for col in range(1, 8): ws.cell(row=r, column=col).fill = BAND; ws.cell(row=r, column=col).border = BOX
        r += 1
        first = r
        for n, iid in enumerate(ids, 1):
            it = items[iid]
            ws.cell(row=r, column=1, value=f"{code}.{n}")
            ws.cell(row=r, column=2, value=it["name"]); ws.cell(row=r, column=3, value=it["unit"])
            ws.cell(row=r, column=4, value=it["qty"]); ws.cell(row=r, column=5, value=rt[iid])
            ws.cell(row=r, column=6, value=f"=D{r}*E{r}"); ws.cell(row=r, column=7, value=it["basis"])
            for col in range(1, 8):
                ws.cell(row=r, column=col).border = BOX
                ws.cell(row=r, column=col).alignment = Alignment(wrap_text=True, vertical="top")
            r += 1
        ws.cell(row=r, column=2, value=f"Sub-total {code}").font = Font(bold=True)
        ws.cell(row=r, column=6, value=f"=SUM(F{first}:F{r-1})").font = Font(bold=True)
        for col in range(1, 8): ws.cell(row=r, column=col).border = BOX
        group_rows.append((code, title, r))
        r += 2
    for col, w in zip("ABCDEFG", (7, 44, 8, 12, 13, 16, 70)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=7, max_row=r, min_col=4, max_col=6):
        for c in row:
            c.number_format = "#,##0.00" if c.column == 4 else "#,##0"
    ws.freeze_panes = "A7"
    # ---------------- Abstract
    ab = wb.create_sheet("Abstract of Cost", 0)
    ab["A1"] = "ABSTRACT OF COST (PRELIMINARY ESTIMATE)"; ab["A1"].font = Font(bold=True, size=14)
    ab["A2"] = f"Project: {project_name}   |   Revision {revision}   |   {dt.date.today().isoformat()}"
    _hdr(ab, 4, ["Sr.", "Head of work", "Amount (INR)", "% of base cost"])
    rr = 5
    for code, title, srow in group_rows:
        ab.cell(row=rr, column=1, value=code); ab.cell(row=rr, column=2, value=title)
        ab.cell(row=rr, column=3, value=f"=BOQ!F{srow}")
        for col in range(1, 5): ab.cell(row=rr, column=col).border = BOX
        rr += 1
    first, last = 5, rr - 1
    ab.cell(row=rr, column=2, value="BASE COST").font = Font(bold=True); ab.cell(row=rr, column=3, value=f"=SUM(C{first}:C{last})").font = Font(bold=True)
    base = rr; rr += 1
    ab.cell(row=rr, column=2, value=f"Contingency @ {contingency_pct:g}%"); ab.cell(row=rr, column=3, value=f"=C{base}*{contingency_pct / 100}")
    cont = rr; rr += 1
    ab.cell(row=rr, column=2, value="ESTIMATED TOTAL (excl. taxes, land, approvals, furniture)").font = Font(bold=True)
    ab.cell(row=rr, column=3, value=f"=C{base}+C{cont}").font = Font(bold=True)
    tot = rr; rr += 1
    ab.cell(row=rr, column=2, value="Approx. rate per m2 of built-up area"); ab.cell(row=rr, column=3, value=f"=C{tot}/{max(est['built_up_m2'], 1)}")
    for rw in range(first, rr + 1):
        for col in range(1, 5):
            ab.cell(row=rw, column=col).border = BOX
        ab.cell(row=rw, column=3).number_format = "#,##0"
        if rw <= last or rw == base:
            ab.cell(row=rw, column=4, value=f"=C{rw}/C{base}").number_format = "0.0%"
    ab.column_dimensions["A"].width = 7; ab.column_dimensions["B"].width = 62; ab.column_dimensions["C"].width = 18; ab.column_dimensions["D"].width = 14
    ab.cell(row=rr + 2, column=1, value=est["disclaimer"]).alignment = Alignment(wrap_text=True, vertical="top")
    ab.merge_cells(start_row=rr + 2, start_column=1, end_row=rr + 6, end_column=4)
    # ---------------- Structure
    sp = prelim(model)
    st = wb.create_sheet("Structure (prelim)")
    st["A1"] = "PRELIMINARY STRUCTURAL SIZES - NOT A STRUCTURAL DESIGN"; st["A1"].font = Font(bold=True, size=13, color="B00020")
    _hdr(st, 3, ["Member", "Size / value", "Basis", "Note"])
    for i, it in enumerate(sp["items"], 4):
        for j, v in enumerate((it["name"], it["value"], it["basis"], it.get("note", "")), 1):
            c = st.cell(row=i, column=j, value=v); c.border = BOX; c.alignment = Alignment(wrap_text=True, vertical="top")
    k = 4 + len(sp["items"]) + 1
    for n, (a, b) in enumerate(sp["assumptions"].items()):
        st.cell(row=k + n, column=1, value=a); st.cell(row=k + n, column=2, value=str(b))
    st.cell(row=k + len(sp["assumptions"]) + 1, column=1, value=sp["disclaimer"]).alignment = Alignment(wrap_text=True, vertical="top")
    st.merge_cells(start_row=k + len(sp["assumptions"]) + 1, start_column=1, end_row=k + len(sp["assumptions"]) + 5, end_column=4)
    for col, w in zip("ABCD", (30, 26, 70, 50)):
        st.column_dimensions[col].width = w
    # ---------------- Rooms
    rm = wb.create_sheet("Room areas")
    from .layout import room_metrics
    _hdr(rm, 1, ["Floor", "Room", "Clear size (mm)", "Area (m2)"])
    for i, s in enumerate(model.spaces, 2):
        m = room_metrics(model, s)
        for j, v in enumerate((model.level(s.level).name, s.name, f"{m['clear_w']:.0f} x {m['clear_d']:.0f}", round(m["area_m2"], 2)), 1):
            rm.cell(row=i, column=j, value=v).border = BOX
    for col, w in zip("ABCD", (16, 28, 20, 12)):
        rm.column_dimensions[col].width = w
    for w_ in wb.worksheets:
        w_.sheet_view.showGridLines = False
        w_.page_setup.orientation = "landscape"; w_.page_setup.fitToWidth = 1
    bio = io.BytesIO(); wb.save(bio)
    return bio.getvalue()
