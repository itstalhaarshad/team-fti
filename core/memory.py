"""Shared memory store — persistent, append-only, auditable, file-backed.

One directory per batch under data/batches/<batch_id>/:
  rubric.json    - written once by the Rubric Architect
  ledger.jsonl   - PRECEDENT / CONSISTENCY ledger (append-only): one graded answer per line.
                   This is the core product value: same answer -> same marks across students.
  results.json   - per-student results (mutable via teacher edits)
  summaries.json - per-student summaries
  audit.jsonl    - append-only log of every write, so decisions are traceable

The store is exposed to the agents; the orchestrator coordinates reads/writes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from core.schemas import Precedent, Rubric, StudentResult, StudentSummary

BATCHES_ROOT = Path("data/batches")


class Memory:
    def __init__(self, batch_id: str):
        self.batch_id = batch_id
        self.dir = BATCHES_ROOT / batch_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.rubric_path = self.dir / "rubric.json"
        self.ledger_path = self.dir / "ledger.jsonl"
        self.results_path = self.dir / "results.json"
        self.summaries_path = self.dir / "summaries.json"
        self.audit_path = self.dir / "audit.jsonl"

    # ---- audit (append-only) ----
    def _audit(self, action: str, detail: dict) -> None:
        with self.audit_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"action": action, **detail}, ensure_ascii=False) + "\n")

    # ---- rubric (written once) ----
    def save_rubric(self, rubric: Rubric) -> None:
        self.rubric_path.write_text(rubric.model_dump_json(indent=2), encoding="utf-8")
        self._audit("save_rubric", {"title": rubric.title, "questions": len(rubric.questions)})

    def load_rubric(self) -> Optional[Rubric]:
        if not self.rubric_path.exists():
            return None
        return Rubric.model_validate_json(self.rubric_path.read_text(encoding="utf-8"))

    # ---- precedent / consistency ledger (append-only) ----
    def append_precedent(self, precedent: Precedent) -> None:
        with self.ledger_path.open("a", encoding="utf-8") as f:
            f.write(precedent.model_dump_json() + "\n")
        self._audit("append_precedent",
                    {"question": precedent.question, "marks": precedent.awarded_marks,
                     "source_student": precedent.source_student})

    def load_precedents(self, question: Optional[str] = None) -> List[Precedent]:
        if not self.ledger_path.exists():
            return []
        out: List[Precedent] = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                p = Precedent.model_validate_json(line)
                if question is None or p.question == question:
                    out.append(p)
        return out

    # ---- results (mutable; every edit audited) ----
    def _read_results(self) -> Dict[str, dict]:
        if not self.results_path.exists():
            return {}
        return json.loads(self.results_path.read_text(encoding="utf-8"))

    def save_result(self, result: StudentResult) -> None:
        data = self._read_results()
        data[result.student_id] = result.model_dump()
        self.results_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self._audit("save_result",
                    {"student_id": result.student_id,
                     "total": result.total_awarded, "max": result.total_max,
                     "flags": len(result.open_flags)})

    def load_results(self) -> Dict[str, StudentResult]:
        return {sid: StudentResult.model_validate(r) for sid, r in self._read_results().items()}

    def edit_score(self, student_id: str, question: str, new_marks: float,
                   by: str = "teacher") -> None:
        """Teacher override of one question's score; clears the flag and audits the change."""
        data = self._read_results()
        result = StudentResult.model_validate(data[student_id])
        for a in result.answers:
            if a.number == question:
                old = a.awarded_marks
                a.awarded_marks = max(0.0, min(new_marks, a.max_marks))
                a.flagged = False
                a.flag_reason = None
                self._audit("edit_score",
                            {"student_id": student_id, "question": question,
                             "old": old, "new": a.awarded_marks, "by": by})
                break
        data[student_id] = result.model_dump()
        self.results_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- summaries ----
    def save_summary(self, summary: StudentSummary) -> None:
        data = json.loads(self.summaries_path.read_text(encoding="utf-8")) \
            if self.summaries_path.exists() else {}
        data[summary.student_id] = summary.model_dump()
        self.summaries_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self._audit("save_summary", {"student_id": summary.student_id})

    def load_summaries(self) -> Dict[str, StudentSummary]:
        if not self.summaries_path.exists():
            return {}
        data = json.loads(self.summaries_path.read_text(encoding="utf-8"))
        return {sid: StudentSummary.model_validate(s) for sid, s in data.items()}
