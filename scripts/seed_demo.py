"""Seed a realistic, already-graded demo batch into Firestore — a safety net for live demos.

If the live grading ever flops (API hiccup, bad scan, no Wi-Fi), log in as the demo account and
show this pre-graded batch instead. No Gemini calls — the data is baked in here.

Usage:
    python scripts/seed_demo.py                      # demo@gradepanel.app / demo123456
    python scripts/seed_demo.py you@email.com pass   # seed into your own account

Requires Firebase configured in .env (STORAGE_BACKEND=firestore, FIREBASE_WEB_API_KEY,
FIREBASE_SERVICE_ACCOUNT).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import auth
from core.store import get_store
from core.schemas import (BatchMeta, Confidence, FlagReason, GradedAnswer,
                          Precedent, QuestionRubric, Rubric, StudentResult,
                          StudentSummary)

DEMO_EMAIL = "demo@gradepanel.app"
DEMO_PASSWORD = "demo123456"
BATCH_ID = "demo-functional-english-final"

RUBRIC = Rubric(title="Functional English — Final-term 2026", questions=[
    QuestionRubric(number="1", max_marks=20.0,
                   model_answer="Define & exemplify four sentence types: optative (wish/prayer), "
                                "exclamatory (strong emotion, ends with !), complex (one independent "
                                "+ ≥1 dependent clause), compound (≥2 independent clauses joined by a "
                                "coordinating conjunction). 5 marks each (3 definition + 2 example).",
                   key_points=["Optative: wish/prayer/desire (5)", "Exclamatory: strong emotion, '!' (5)",
                               "Complex: 1 independent + dependent clause (5)",
                               "Compound: 2+ independent clauses + conjunction (5)"]),
    QuestionRubric(number="2", max_marks=10.0,
                   model_answer="Inclusive language avoids bias/stereotypes and respects all people; "
                                "promotes equality by fostering belonging and reducing prejudice.",
                   key_points=["Accurate definition (4)", "How it promotes equality/respect (4)",
                               "Examples (1)", "Organization & language (1)"]),
    QuestionRubric(number="3", max_marks=10.0,
                   model_answer="Public speaking = delivering a speech to a live audience. Barriers: "
                                "fear/anxiety, poor preparation, weak delivery, audience disengagement; "
                                "overcome via practice, breathing, audience analysis, engaging delivery.",
                   key_points=["Definition (2)", "Identify & explain barriers (4)",
                               "Ways to overcome them (3)", "Organization & language (1)"]),
    QuestionRubric(number="4", max_marks=10.0,
                   model_answer="The Seven Cs: Clear, Concise, Concrete, Correct, Coherent, Complete, "
                                "Courteous — each explained with a practical example.",
                   key_points=["Identify all 7 Cs (1)", "Explain each C (6)", "Examples (2)",
                               "Organization & language (1)"]),
])


def _ans(n, marks, mx, text, why, conf=Confidence.high, flagged=False, reason=None):
    return GradedAnswer(number=n, transcribed_answer=text, awarded_marks=marks, max_marks=mx,
                        reasoning=why, confidence=conf, flagged=flagged, flag_reason=reason)


STUDENTS = {
    "Ayesha (Roll 01)": ([
        _ans("1", 18.0, 20, "Clear, correct definitions and examples for all four sentence types; "
             "minor slip on the compound example.",
             "Optative, exclamatory and complex fully correct (15/15). Compound definition correct, "
             "one example weak (3/5)."),
        _ans("2", 9.0, 10, "Strong definition of inclusive language with gender-neutral examples and a "
             "clear equality argument.",
             "Definition (4/4), equality explanation (4/4), examples (1/1), minor language errors (0/1)."),
        _ans("3", 8.0, 10, "Defines public speaking and explains three barriers with remedies.",
             "Definition (2/2), three barriers explained (3/4), remedies (3/3), language (0/1)."),
        _ans("4", 6.0, 10, "Lists all seven Cs; explanations thin for Concrete and Coherent.",
             "All 7 identified (1/1), explanations partial (4/6), one example (1/2)."),
    ], "Ayesha shows strong command of sentence types and inclusive language; tighten explanations "
       "for the Seven Cs.", "Excellent work on definitions and inclusive language. To reach full marks, "
       "give a worked example for every 'C' and proofread for small grammar slips."),

    "Bilal (Roll 02)": ([
        _ans("1", 12.0, 20, "Optative and exclamatory correct; complex sentence definition confuses "
             "independent/dependent clauses; one sub-answer is too faint to read.",
             "Optative (5/5), exclamatory (4/5), complex partial (3/5). Compound sub-answer flagged."),
        _ans("2", 7.0, 10, "Good definition; equality discussion brief.",
             "Definition (4/4), equality explanation (2/4), examples (1/1)."),
        _ans("3", 8.0, 10, "Solid barriers and remedies.",
             "Definition (2/2), barriers (4/4), remedies (2/3)."),
        _ans("1c", 0.0, 0, "", "Compound-sentence sub-answer is too faint/smudged to read confidently — "
             "needs the teacher to confirm.", conf=Confidence.low, flagged=True, reason=FlagReason.unreadable),
    ], "Bilal is solid overall but one Q1 sub-answer couldn't be read and is flagged for review.",
       "Good grasp of public speaking and inclusive language. Please rewrite the smudged compound-"
       "sentence answer so it can be marked."),

    "Hina (Roll 03)": ([
        _ans("1", 9.0, 20, "Definitions partly correct; several examples missing or incorrect.",
             "Optative (3/5), exclamatory (3/5), complex (2/5), compound (1/5)."),
        _ans("2", 6.0, 10, "Basic definition; limited examples.",
             "Definition (3/4), equality explanation (2/4), examples (1/1)."),
        _ans("3", 5.0, 10, "Defines public speaking but lists general tips rather than barriers.",
             "Definition (2/2), barriers not clearly identified (2/4), remedies (1/3)."),
        _ans("4", 4.0, 10, "Identifies the Cs but few explanations or examples.",
             "All 7 named (1/1), explanations weak (2/6), examples (1/2)."),
    ], "Hina understands the basics but needs more complete definitions and examples across the paper.",
       "You're on the right track. Focus on giving a clear definition AND an example for each item, and "
       "frame Q3 around 'barriers' specifically."),
}


def main():
    email = sys.argv[1] if len(sys.argv) > 1 else DEMO_EMAIL
    password = sys.argv[2] if len(sys.argv) > 2 else DEMO_PASSWORD

    try:
        sess = auth.sign_up(email, password); print(f"Created demo account {email}")
    except auth.AuthError:
        sess = auth.sign_in(email, password); print(f"Using existing account {email}")
    uid = sess["uid"]

    store = get_store(BATCH_ID, uid)
    store.save_meta(BatchMeta(batch_id=BATCH_ID, name=RUBRIC.title, subject="English",
                              session="Final-term 2026", created_at="2026-06-17 10:00"))
    store.save_rubric(RUBRIC)

    for sid, (answers, summary, feedback) in STUDENTS.items():
        result = StudentResult(student_id=sid, answers=answers)
        store.save_result(result)
        store.save_summary(StudentSummary(student_id=sid, summary=summary, feedback=feedback,
                                          pending_review=[a.number for a in result.open_flags]))
        # grow the consistency ledger with a couple of precedents per student
        for a in answers:
            if not a.flagged and a.confidence != Confidence.low:
                store.append_precedent(Precedent(question=a.number,
                                                 answer_fingerprint=a.transcribed_answer[:80],
                                                 awarded_marks=a.awarded_marks, reason=a.reasoning,
                                                 source_student=sid))

    print(f"Seeded batch '{RUBRIC.title}' with {len(STUDENTS)} students.")
    print(f"Log in at the app as: {email} / {password}")


if __name__ == "__main__":
    main()
