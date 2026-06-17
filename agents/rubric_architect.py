"""Agent 1 — Rubric Architect (runs once per batch).

Turns a sample/model answer sheet image and/or free-text guidelines into a structured Rubric
(per-question model answer + max marks + key points). The orchestrator writes it to shared memory.
"""
from __future__ import annotations

from typing import List, Optional

from core.llm import Part, generate_json
from core.schemas import Rubric

SYSTEM = (
    "You are the Rubric Architect on an examiner panel. Your job is to turn a teacher's marking "
    "scheme into a precise, structured rubric that other examiners will grade against. "
    "Read any provided model-answer image AND the written guidelines. For EACH question produce: "
    "the question number, the maximum marks, a clear model answer, and the discrete key points a "
    "student must hit to earn marks. Preserve the teacher's mark allocation exactly. If marks for a "
    "question are not stated anywhere, infer a sensible value and keep it consistent. Do not invent "
    "questions that aren't supported by the inputs."
)


def build_rubric(
    title: str,
    guidelines: Optional[str] = None,
    answer_key_parts: Optional[List[Part]] = None,
) -> Rubric:
    """Build a structured Rubric from guidelines text and/or a model-answer image."""
    if not guidelines and not answer_key_parts:
        raise ValueError("Provide guidelines text and/or an answer-key image to build a rubric.")

    parts: List[Part] = [f"Batch title: {title}"]
    if guidelines:
        parts.append("Teacher's written marking guidelines:\n" + guidelines)
    if answer_key_parts:
        parts.append("Model/sample answer sheet image(s) follow:")
        parts.extend(answer_key_parts)
    parts.append("Produce the structured rubric now.")

    rubric = generate_json(parts, schema=Rubric, system=SYSTEM)
    if not rubric.title:
        rubric.title = title
    return rubric
