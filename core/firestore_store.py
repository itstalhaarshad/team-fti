"""Firestore storage backend (Firebase Admin SDK). Mirrors core.memory.Memory's API.

Layout:  users/{uid}/batches/{batch_id}  document = {meta, rubric}
         .../results/{student_id}, .../summaries/{student_id}, .../ledger/*, .../audit/*

Student sheet images are kept on local disk (Firestore documents cap at ~1 MB); moving them to
Firebase Storage is a follow-up. Everything else (rubric, results, ledger, summaries, meta,
audit) lives in Firestore, scoped to the signed-in teacher.

Activated only when STORAGE_BACKEND=firestore; needs FIREBASE_SERVICE_ACCOUNT.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional

from core.llm import ImagePart
from core.memory import Memory
from core.schemas import (BatchMeta, GradedAnswer, Precedent, Rubric,
                          StudentResult, StudentSummary)

_client = None


def _db():
    global _client
    if _client is None:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            sa = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "firebase-service-account.json")
            if not os.path.exists(sa):
                raise RuntimeError(f"Firebase service account not found at {sa!r} "
                                   "(set FIREBASE_SERVICE_ACCOUNT).")
            firebase_admin.initialize_app(credentials.Certificate(sa))
        _client = firestore.client()
    return _client


class FirestoreStore:
    def __init__(self, batch_id: str, uid: Optional[str]):
        if not uid:
            raise ValueError("Firestore backend requires a signed-in uid.")
        self.batch_id = batch_id
        self.uid = uid
        self._doc = (_db().collection("users").document(uid)
                     .collection("batches").document(batch_id))
        # sheet blobs stay on local disk, namespaced by user+batch
        self._sheets = Memory(f"{uid}/{batch_id}")

    # ---- audit ----
    def _audit(self, action: str, detail: dict) -> None:
        self._doc.collection("audit").add({"action": action, "at": datetime.utcnow().isoformat(), **detail})

    # ---- meta ----
    def save_meta(self, meta: BatchMeta) -> None:
        self._doc.set({"meta": meta.model_dump()}, merge=True)
        self._audit("save_meta", {"name": meta.name})

    def load_meta(self) -> Optional[BatchMeta]:
        snap = self._doc.get()
        data = snap.to_dict() if snap.exists else None
        return BatchMeta.model_validate(data["meta"]) if data and data.get("meta") else None

    # ---- rubric ----
    def save_rubric(self, rubric: Rubric) -> None:
        self._doc.set({"rubric": rubric.model_dump()}, merge=True)
        self._audit("save_rubric", {"questions": len(rubric.questions)})

    def load_rubric(self) -> Optional[Rubric]:
        snap = self._doc.get()
        data = snap.to_dict() if snap.exists else None
        return Rubric.model_validate(data["rubric"]) if data and data.get("rubric") else None

    # ---- precedent ledger ----
    def append_precedent(self, precedent: Precedent) -> None:
        self._doc.collection("ledger").add(precedent.model_dump())
        self._audit("append_precedent",
                    {"question": precedent.question, "marks": precedent.awarded_marks})

    def load_precedents(self, question: Optional[str] = None) -> List[Precedent]:
        col = self._doc.collection("ledger")
        docs = col.where("question", "==", question).stream() if question else col.stream()
        return [Precedent.model_validate(d.to_dict()) for d in docs]

    # ---- results ----
    def save_result(self, result: StudentResult) -> None:
        self._doc.collection("results").document(result.student_id).set(result.model_dump())
        self._audit("save_result", {"student_id": result.student_id, "total": result.total_awarded})

    def load_results(self) -> Dict[str, StudentResult]:
        return {d.id: StudentResult.model_validate(d.to_dict())
                for d in self._doc.collection("results").stream()}

    def edit_score(self, student_id: str, question: str, new_marks: float, by: str = "teacher") -> None:
        ref = self._doc.collection("results").document(student_id)
        result = StudentResult.model_validate(ref.get().to_dict())
        for a in result.answers:
            if a.number == question:
                old = a.awarded_marks
                a.awarded_marks = max(0.0, min(new_marks, a.max_marks))
                a.flagged, a.flag_reason = False, None
                self._audit("edit_score", {"student_id": student_id, "question": question,
                                           "old": old, "new": a.awarded_marks, "by": by})
                break
        ref.set(result.model_dump())

    def replace_answer(self, student_id: str, answer: GradedAnswer, by: str = "ai-regrade") -> None:
        ref = self._doc.collection("results").document(student_id)
        result = StudentResult.model_validate(ref.get().to_dict())
        for idx, a in enumerate(result.answers):
            if a.number == answer.number:
                self._audit("regrade", {"student_id": student_id, "question": answer.number,
                                        "old": a.awarded_marks, "new": answer.awarded_marks, "by": by})
                result.answers[idx] = answer
                break
        ref.set(result.model_dump())

    # ---- summaries ----
    def save_summary(self, summary: StudentSummary) -> None:
        self._doc.collection("summaries").document(summary.student_id).set(summary.model_dump())
        self._audit("save_summary", {"student_id": summary.student_id})

    def load_summaries(self) -> Dict[str, StudentSummary]:
        return {d.id: StudentSummary.model_validate(d.to_dict())
                for d in self._doc.collection("summaries").stream()}

    # ---- sheets (local disk) ----
    def save_sheet_parts(self, student_id: str, parts: List[ImagePart]) -> None:
        self._sheets.save_sheet_parts(student_id, parts)

    def load_sheet_parts(self, student_id: str) -> List[ImagePart]:
        return self._sheets.load_sheet_parts(student_id)


def list_batches_fs(uid: Optional[str]) -> List[dict]:
    """Summaries of a teacher's Firestore batches, newest first."""
    if not uid:
        return []
    out: List[dict] = []
    col = _db().collection("users").document(uid).collection("batches")
    for doc in col.stream():
        data = doc.to_dict() or {}
        meta = data.get("meta", {})
        rubric = Rubric.model_validate(data["rubric"]) if data.get("rubric") else None
        results = {d.id: StudentResult.model_validate(d.to_dict())
                   for d in col.document(doc.id).collection("results").stream()}
        n = len(results)
        avg = sum(r.total_awarded for r in results.values()) / n if n else 0.0
        out.append({
            "batch_id": doc.id,
            "name": meta.get("name") or (rubric.title if rubric else doc.id),
            "subject": meta.get("subject", "—"),
            "session": meta.get("session", "—"),
            "created": meta.get("created_at", ""),
            "n_students": n,
            "avg": avg,
            "total_marks": rubric.total_marks if rubric else 0.0,
            "flags": sum(len(r.open_flags) for r in results.values()),
            "_mtime": meta.get("created_at", ""),
        })
    out.sort(key=lambda b: (b["created"], b["_mtime"]), reverse=True)
    return out
