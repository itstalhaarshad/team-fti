"""Plain-Python orchestration of the 3-agent panel over a batch (sequential).

  1. Rubric Architect once -> rubric in shared memory.
  2. Per student sheet: Grader -> write precedents for confident answers -> Summarizer.
  3. Return a batch view (students + totals + open flags) for the dashboard.

No agent framework — just functions calling our own vision wrapper as their tool, coordinating
through the file-backed Memory store.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from agents.grader import grade_sheet, regrade_question
from agents.rubric_architect import build_rubric
from agents.summarizer import summarize
from core.llm import ImagePart, Part
from core.memory import Memory
from core.schemas import (Confidence, Precedent, Rubric, StudentResult,
                          StudentSummary)


@dataclass
class StudentSheet:
    student_id: str
    parts: List[Part]


@dataclass
class BatchView:
    batch_id: str
    rubric: Rubric
    results: Dict[str, StudentResult] = field(default_factory=dict)
    summaries: Dict[str, StudentSummary] = field(default_factory=dict)

    @property
    def total_open_flags(self) -> int:
        return sum(len(r.open_flags) for r in self.results.values())


def _fingerprint(answer_text: str, limit: int = 120) -> str:
    """Short normalized form of an answer for precedent matching/display."""
    return " ".join(answer_text.split())[:limit]


def setup_rubric(batch_id: str, title: str, guidelines: Optional[str] = None,
                 answer_key_parts: Optional[List[Part]] = None) -> Rubric:
    """Agent 1: build the rubric once and persist it to shared memory."""
    mem = Memory(batch_id)
    rubric = build_rubric(title, guidelines=guidelines, answer_key_parts=answer_key_parts)
    mem.save_rubric(rubric)
    return rubric


def grade_student(batch_id: str, sheet: StudentSheet) -> tuple[StudentResult, StudentSummary]:
    """Agents 2+3 for one student: grade against rubric+precedents, write precedents, summarize."""
    mem = Memory(batch_id)
    rubric = mem.load_rubric()
    if rubric is None:
        raise RuntimeError(f"No rubric in memory for batch {batch_id}; run setup_rubric first.")

    image_parts = [p for p in sheet.parts if isinstance(p, ImagePart)]
    mem.save_sheet_parts(sheet.student_id, image_parts)  # keep sheets for the re-grade loop
    precedents = mem.load_precedents()
    result = grade_sheet(sheet.student_id, sheet.parts, rubric, precedents)
    mem.save_result(result)

    # Write a precedent for each confidently-graded answer (the consistency ledger grows).
    for a in result.answers:
        if not a.flagged and a.confidence != Confidence.low:
            mem.append_precedent(Precedent(
                question=a.number,
                answer_fingerprint=_fingerprint(a.transcribed_answer),
                awarded_marks=a.awarded_marks,
                reason=a.reasoning,
                source_student=sheet.student_id,
            ))

    summary = summarize(result)
    mem.save_summary(summary)
    return result, summary


def regrade_flagged(batch_id: str, student_id: str, question_number: str,
                    clarification: str) -> StudentResult:
    """Teacher-in-the-loop: re-grade ONE flagged question with the teacher's clarification.

    Reloads the stored sheet, re-grades just that question, persists the new answer, and (if it's
    now confidently graded) appends a precedent so the clarification benefits later students too.
    """
    mem = Memory(batch_id)
    rubric = mem.load_rubric()
    if rubric is None:
        raise RuntimeError(f"No rubric for batch {batch_id}.")
    parts = mem.load_sheet_parts(student_id)
    if not parts:
        raise RuntimeError(f"No stored sheet for {student_id}; cannot re-grade.")

    answer = regrade_question(student_id, parts, rubric, question_number, clarification,
                              mem.load_precedents(question_number))
    mem.replace_answer(student_id, answer)
    if not answer.flagged and answer.confidence != Confidence.low:
        mem.append_precedent(Precedent(
            question=answer.number,
            answer_fingerprint=_fingerprint(answer.transcribed_answer),
            awarded_marks=answer.awarded_marks,
            reason=answer.reasoning,
            source_student=student_id,
        ))
    return mem.load_results()[student_id]


def run_batch(batch_id: str, title: str, sheets: List[StudentSheet],
              guidelines: Optional[str] = None,
              answer_key_parts: Optional[List[Part]] = None,
              rubric: Optional[Rubric] = None) -> BatchView:
    """End-to-end: build rubric (unless provided) then grade every student sequentially."""
    mem = Memory(batch_id)
    if rubric is None and mem.load_rubric() is None:
        rubric = setup_rubric(batch_id, title, guidelines, answer_key_parts)
    else:
        rubric = rubric or mem.load_rubric()

    view = BatchView(batch_id=batch_id, rubric=rubric)
    for sheet in sheets:
        result, summary = grade_student(batch_id, sheet)
        view.results[sheet.student_id] = result
        view.summaries[sheet.student_id] = summary
    return view
