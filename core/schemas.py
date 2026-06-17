"""Shared data contracts (Pydantic) used by agents, memory, UI, and export.

These doubles as the structured-output schemas we hand to the LLM wrapper, so the
grader returns machine-readable JSON the dashboard can render directly.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class FlagReason(str, Enum):
    unreadable = "unreadable"      # handwriting can't be read confidently
    ambiguous = "ambiguous"        # answer is readable but grading is uncertain
    off_rubric = "off_rubric"      # answer doesn't map to any rubric question
    missing = "missing"            # no answer found for this question


# ---- Rubric (Agent 1 output) ----
class QuestionRubric(BaseModel):
    number: str = Field(description="Question identifier, e.g. '1', '2a'.")
    max_marks: float
    model_answer: str = Field(description="The expected/model answer.")
    key_points: List[str] = Field(default_factory=list, description="Markable points.")


class Rubric(BaseModel):
    title: str = Field(default="Untitled batch")
    questions: List[QuestionRubric]

    @property
    def total_marks(self) -> float:
        return sum(q.max_marks for q in self.questions)


# ---- Grading (Agent 2 output, per question) ----
class GradedAnswer(BaseModel):
    number: str
    transcribed_answer: str = Field(description="What the student wrote, as read by the model.")
    awarded_marks: float
    max_marks: float
    reasoning: str = Field(description="Why these marks — cite rubric points.")
    confidence: Confidence
    flagged: bool = False
    flag_reason: Optional[FlagReason] = None


class StudentResult(BaseModel):
    student_id: str
    answers: List[GradedAnswer]

    @property
    def total_awarded(self) -> float:
        return sum(a.awarded_marks for a in self.answers if not a.flagged)

    @property
    def total_max(self) -> float:
        return sum(a.max_marks for a in self.answers)

    @property
    def open_flags(self) -> List[GradedAnswer]:
        return [a for a in self.answers if a.flagged]


# GraderOutput is the raw structured-output schema we hand the LLM (no student_id —
# the orchestrator attaches that). Kept separate from StudentResult so the model only
# decides per-question grading, not bookkeeping.
class GraderOutput(BaseModel):
    answers: List[GradedAnswer]


# ---- Summary (Agent 3 output) ----
class StudentSummary(BaseModel):
    student_id: str
    summary: str
    feedback: str
    pending_review: List[str] = Field(default_factory=list, description="Question numbers to review.")


# SummarizerOutput is what the LLM returns (no student_id — attached by the orchestrator).
class SummarizerOutput(BaseModel):
    summary: str
    feedback: str
    pending_review: List[str] = Field(default_factory=list)


# ---- Precedent ledger entry (shared memory, append-only) ----
class Precedent(BaseModel):
    question: str
    answer_fingerprint: str = Field(description="Normalized/short form of the answer for matching.")
    awarded_marks: float
    reason: str
    source_student: str
