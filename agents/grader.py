"""Agent 2 — Grader / First Marker (per student sheet).

Reads handwriting AND grades vs the rubric in one vision pass. Grades confident answers,
appends a precedent per graded answer, and FLAGS low-confidence/unreadable answers instead
of guessing. Shown relevant precedents so equivalent answers get equal marks across students.

TODO(phase1): grade_sheet(student_id, parts, rubric, precedents) -> StudentResult.
"""
