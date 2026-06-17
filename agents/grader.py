"""Agent 2 — Grader / First Marker (per student sheet).

Reads the handwriting AND grades against the rubric in ONE vision pass. Grades confident
answers, and FLAGS low-confidence / unreadable / ambiguous answers instead of guessing.

Consistency: the grader is shown relevant PRECEDENTS (how equivalent answers were already
marked) so the same answer earns the same mark across all students in the batch.
"""
from __future__ import annotations

from typing import List, Optional

from core.llm import Part, generate_json
from core.schemas import Confidence, GradedAnswer, GraderOutput, Precedent, Rubric, StudentResult

SYSTEM = (
    "You are the Grader (First Marker) on an examiner panel. You read handwritten student answers "
    "from images and grade them against a fixed rubric in a single pass. Rules:\n"
    "1. For each rubric question, find and transcribe the student's answer as faithfully as you can.\n"
    "2. Grade ONLY against the rubric's model answer and key points. Award partial marks for "
    "partially-correct answers, citing which key points were met in your reasoning.\n"
    "3. Set confidence: 'high' when the handwriting is clearly legible and grading is unambiguous; "
    "'medium' when mostly readable; 'low' when you are unsure.\n"
    "4. If you CANNOT read the answer confidently, or it is ambiguous, missing, or doesn't match any "
    "rubric question, set flagged=true with the right flag_reason and DO NOT guess a score — set "
    "awarded_marks=0 and explain what a teacher needs to resolve. Never fabricate an answer.\n"
    "5. Be CONSISTENT with the provided precedents: if a student's answer is equivalent to a "
    "precedent, award the same marks for the same reason.\n"
    "Return one entry per rubric question, in rubric order."
)


def _format_precedents(precedents: List[Precedent]) -> str:
    if not precedents:
        return "No precedents yet — you are setting the standard for this batch."
    lines = ["Precedents (how equivalent answers were already marked — stay consistent):"]
    for p in precedents:
        lines.append(
            f"- Q{p.question}: answer ~ \"{p.answer_fingerprint}\" -> {p.awarded_marks} marks "
            f"({p.reason})"
        )
    return "\n".join(lines)


def grade_sheet(
    student_id: str,
    sheet_parts: List[Part],
    rubric: Rubric,
    precedents: Optional[List[Precedent]] = None,
) -> StudentResult:
    """Grade one student's sheet against the rubric, returning per-question results."""
    parts: List[Part] = [
        f"Student id: {student_id}",
        "RUBRIC (grade strictly against this):\n" + rubric.model_dump_json(indent=2),
        _format_precedents(precedents or []),
        "The student's answer sheet image(s) follow. Grade every rubric question now.",
    ]
    parts.extend(sheet_parts)

    out: GraderOutput = generate_json(parts, schema=GraderOutput, system=SYSTEM)

    # Enforce max_marks from the rubric (don't trust the model to echo it) and clamp scores.
    max_by_q = {q.number: q.max_marks for q in rubric.questions}
    answers: List[GradedAnswer] = []
    for a in out.answers:
        a.max_marks = max_by_q.get(a.number, a.max_marks)
        a.awarded_marks = max(0.0, min(a.awarded_marks, a.max_marks))
        if a.flagged:
            a.awarded_marks = 0.0
        answers.append(a)

    return StudentResult(student_id=student_id, answers=answers)


REGRADE_SYSTEM = (
    SYSTEM + "\n\nThis is a RE-GRADE of a single previously-flagged question. The teacher has "
    "added a clarification — treat it as authoritative context for reading or interpreting the "
    "answer. Look again carefully. Grade it now if you reasonably can; only keep it flagged if it "
    "is still genuinely unreadable or absent."
)


def regrade_question(
    student_id: str,
    sheet_parts: List[Part],
    rubric: Rubric,
    question_number: str,
    clarification: str,
    precedents: Optional[List[Precedent]] = None,
) -> GradedAnswer:
    """Re-grade ONE question for one student, given a teacher clarification. Returns the new answer."""
    q = next((q for q in rubric.questions if q.number == question_number), None)
    if q is None:
        raise ValueError(f"Question {question_number} not in rubric.")

    parts: List[Part] = [
        f"Student id: {student_id}",
        f"Re-grade ONLY question {question_number}.",
        "RUBRIC for this question:\n" + q.model_dump_json(indent=2),
        "Teacher clarification (authoritative):\n" + (clarification or "(none)"),
        _format_precedents(precedents or []),
        f"The student's answer sheet image(s) follow. Transcribe and grade question "
        f"{question_number} now.",
    ]
    parts.extend(sheet_parts)

    ans: GradedAnswer = generate_json(parts, schema=GradedAnswer, system=REGRADE_SYSTEM)
    ans.number = question_number
    ans.max_marks = q.max_marks
    ans.awarded_marks = max(0.0, min(ans.awarded_marks, q.max_marks))
    if ans.flagged:
        ans.awarded_marks = 0.0
    return ans
