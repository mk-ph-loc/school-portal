"""
common.xlsx — Κοινά styling helpers για τα πρότυπα Excel της πύλης (Task 5).

Ενοποιεί το styling που ήταν διπλογραμμένο στα make_template_xlsx() του
Lesson Wizard (4 φύλλα ωραρίου) και του Classroom Hub (ενιαίο 12-φυλλο):
ίδιες μπλε κεφαλίδες, χρωματικός κώδικας πεδίων (🟨 υποχρεωτικά / 🟩
προαιρετικά / 🟥 ευαίσθητα), freeze panes, πλάτη στηλών, tab colors και
ΝΑΙ/ΟΧΙ dropdowns. Οι parsers ΔΕΝ επηρεάζονται (διαβάζουν μόνο τιμές).

Χρήση:
    from common.xlsx import style_sheet, yesno_validation
    style_sheet(ws, headers, widths, req_cols={1, 2}, warn_cols={3})
"""
from __future__ import annotations

# Χρωματικός κώδικας (ίδιος σε όλες τις καρτέλες — εξηγείται στο φύλλο Οδηγίες):
HEAD_FILL = "3F51B5"      # 🟦 κεφαλίδες — ΜΗΝ τις αλλάζετε
REQ_FILL = "FFF9C4"       # 🟨 υποχρεωτικά πεδία
OPT_FILL = "E8F5E9"       # 🟩 προαιρετικά πεδία
WARN_FILL = "FFEBEE"      # 🟥 ευαίσθητα (κωδικοί) — προσοχή
DEFAULT_TAB = "607D8B"    # γκρι-μπλε για άγνωστες καρτέλες


def style_header(ws) -> None:
    """Μπλε bold κεφαλίδα στη γραμμή 1 (minimal styling — πρότυπο ωραρίου)."""
    from openpyxl.styles import Font, PatternFill
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=HEAD_FILL)


def style_sheet(ws, headers: list[str], widths: list[int], req_cols: set[int],
                warn_cols: set[int] | None = None,
                tab_colors: dict[str, str] | None = None) -> None:
    """Πλήρες styling καρτέλας: κεφαλίδες + πλάτη + freeze + tab color +
    χρωματισμός περιοχής εισαγωγής (πρώτες 60 γραμμές) ανά τύπο πεδίου."""
    from openpyxl.styles import Alignment, PatternFill
    from openpyxl.utils import get_column_letter
    ws.append(headers)
    style_header(ws)
    for i, cell in enumerate(ws[1], 1):
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = widths[i - 1] if i <= len(widths) else 18
    ws.freeze_panes = "A2"
    ws.sheet_properties.tabColor = (tab_colors or {}).get(ws.title, DEFAULT_TAB)
    for r in range(2, 62):
        for i in range(1, len(headers) + 1):
            fill = WARN_FILL if (warn_cols and i in warn_cols) else (
                REQ_FILL if i in req_cols else OPT_FILL)
            ws.cell(row=r, column=i).fill = PatternFill("solid", fgColor=fill)


def yesno_validation(ws, cols: list[int]) -> None:
    """Dropdown ΝΑΙ/ΟΧΙ στις στήλες cols (γραμμές 2-200)."""
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.utils import get_column_letter
    dv = DataValidation(type="list", formula1='"ΝΑΙ,ΟΧΙ"', allow_blank=True)
    ws.add_data_validation(dv)
    for col in cols:
        letter = get_column_letter(col)
        dv.add(f"{letter}2:{letter}200")