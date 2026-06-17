"""Batch export to XLSX / CSV.

Builds a teacher-friendly gradebook: one row per student, one column per question, plus totals
and a flag count. Returns bytes so the Streamlit dashboard can offer a download directly.
"""
from __future__ import annotations

import csv
import io
from typing import Dict

from openpyxl import Workbook
from openpyxl.styles import Font

from core.schemas import Rubric, StudentResult


def _headers(rubric: Rubric) -> list[str]:
    return ["Student"] + [f"Q{q.number} (/{q.max_marks:g})" for q in rubric.questions] \
        + ["Total", "Max", "Flags"]


def _row(student_id: str, result: StudentResult, rubric: Rubric) -> list:
    by_q = {a.number: a for a in result.answers}
    cells: list = [student_id]
    for q in rubric.questions:
        a = by_q.get(q.number)
        if a is None:
            cells.append("")
        elif a.flagged:
            cells.append("FLAG")
        else:
            cells.append(a.awarded_marks)
    cells += [result.total_awarded, result.total_max, len(result.open_flags)]
    return cells


def to_xlsx_bytes(rubric: Rubric, results: Dict[str, StudentResult]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Gradebook"
    headers = _headers(rubric)
    ws.append(headers)
    for c in ws[1]:
        c.font = Font(bold=True)
    for sid, result in results.items():
        ws.append(_row(sid, result, rubric))
    for col in ws.columns:
        width = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 40)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_csv_bytes(rubric: Rubric, results: Dict[str, StudentResult]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_headers(rubric))
    for sid, result in results.items():
        w.writerow(_row(sid, result, rubric))
    return buf.getvalue().encode("utf-8")
