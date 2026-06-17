"""Agent 3 — Summarizer (per student sheet).

Produces a short per-student summary + actionable feedback and the list of question numbers
still pending teacher review (the flagged ones). Text-only: it reasons over the grader's output.
"""
from __future__ import annotations

from core.llm import generate_json
from core.schemas import StudentResult, StudentSummary, SummarizerOutput

SYSTEM = (
    "You are the Summarizer on an examiner panel. Given one student's per-question grading results, "
    "write: (1) a 2-3 sentence summary of how they did, (2) brief, specific, encouraging feedback the "
    "teacher could pass to the student, naming concrete strengths and gaps. Do NOT change any scores. "
    "List the question numbers that are flagged for teacher review in pending_review."
)


def summarize(result: StudentResult) -> StudentSummary:
    parts = [
        f"Student id: {result.student_id}",
        f"Total awarded (excluding flagged): {result.total_awarded} / {result.total_max}",
        "Per-question results:\n" + result.model_dump_json(indent=2),
        "Write the summary, feedback, and pending_review list now.",
    ]
    out: SummarizerOutput = generate_json(parts, schema=SummarizerOutput, system=SYSTEM)
    # Trust our own data for the pending list rather than the model's.
    pending = [a.number for a in result.open_flags]
    return StudentSummary(
        student_id=result.student_id,
        summary=out.summary,
        feedback=out.feedback,
        pending_review=pending,
    )
