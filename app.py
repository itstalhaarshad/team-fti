"""GradePanel — Streamlit teacher UI.

Flow: Home (greeting + past batches) -> Foundation (subject + session) -> Start Grading
-> Documents (rubric + exam sheet + answer sheets) -> one-click grade -> Results (review + dashboard).
Coordinates the 3-agent panel via agents.orchestrator over the file-backed shared Memory.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime

import pandas as pd
import streamlit as st

from agents.orchestrator import (StudentSheet, grade_student, regrade_flagged,
                                  setup_rubric)
from core import auth
from core.documents import classify_upload
from core.images import prep_image
from core.llm import ImagePart
from core.store import get_store, list_batches
from core.schemas import BatchMeta, Confidence

st.set_page_config(page_title="GradePanel", page_icon="📝", layout="wide")

CONF_BADGE = {Confidence.high: "🟢 high", Confidence.medium: "🟡 medium", Confidence.low: "🔴 low"}
USER_EMAIL = "itstalhaarshad@gmail.com"
SHEET_TYPES = ["jpg", "jpeg", "png", "webp", "pdf"]
DOC_TYPES = ["docx", "txt", "pdf", "jpg", "jpeg", "png", "webp"]
SUBJECTS = ["English", "Mathematics", "Science", "Urdu", "Computer Science", "Other"]


# --------------------------------------------------------------------------- #
# state                                                                        #
# --------------------------------------------------------------------------- #
def ss():
    s = st.session_state
    s.setdefault("user", None)            # {uid, email, ...} when signed in (None = local mode)
    s.setdefault("step", "home")          # home -> foundation -> documents -> results
    s.setdefault("batch_id", None)
    s.setdefault("batch_name", "")
    s.setdefault("subject", "")
    s.setdefault("session", "")
    s.setdefault("rubric", None)
    s.setdefault("staged", [])            # [{id, parts, files}]
    s.setdefault("uploader_key", 0)
    return s


def current_uid():
    u = ss().user
    return u["uid"] if u else None


def mem():
    return get_store(ss().batch_id, current_uid())


def uploaded_to_part(up) -> ImagePart:
    data = up.getvalue()
    if up.type == "application/pdf" or up.name.lower().endswith(".pdf"):
        return ImagePart(data=data, mime_type="application/pdf")
    return prep_image(data)


def start_batch(subject: str, session: str):
    s = ss()
    name = f"{subject} — {session}"
    slug = re.sub(r"[^a-z0-9]+", "-", f"{subject} {session}".lower()).strip("-") or "batch"
    s.batch_id = f"{slug}-{uuid.uuid4().hex[:6]}"
    s.batch_name, s.subject, s.session = name, subject, session
    s.rubric, s.staged = None, []
    get_store(s.batch_id, current_uid()).save_meta(BatchMeta(
        batch_id=s.batch_id, name=name, subject=subject, session=session,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M")))
    s.step = "documents"


def open_batch(batch_id: str):
    s = ss()
    m = get_store(batch_id, current_uid())
    meta = m.load_meta()
    s.batch_id = batch_id
    s.rubric = m.load_rubric()
    s.batch_name = (meta.name if meta else None) or (s.rubric.title if s.rubric else batch_id)
    s.subject = meta.subject if meta else "—"
    s.session = meta.session if meta else "—"
    s.staged = []
    s.step = "results"


def go_home():
    s = ss()
    s.step, s.batch_id, s.batch_name, s.subject, s.session = "home", None, "", "", ""
    s.rubric, s.staged = None, []


def display_email() -> str:
    u = ss().user
    return u["email"] if u else USER_EMAIL


def render_login():
    st.title("📝 GradePanel")
    st.caption("Sign in to grade and to keep your batches saved to your account.")
    tab_in, tab_up = st.tabs(["Sign in", "Create account"])
    with tab_in:
        e = st.text_input("Email", key="li_email")
        p = st.text_input("Password", type="password", key="li_pw")
        if st.button("Sign in", type="primary", key="li_btn"):
            try:
                ss().user = auth.sign_in(e.strip(), p)
                st.rerun()
            except auth.AuthError as err:
                st.error(str(err))
    with tab_up:
        e2 = st.text_input("Email", key="su_email")
        p2 = st.text_input("Password (min 6 characters)", type="password", key="su_pw")
        if st.button("Create account", type="primary", key="su_btn"):
            try:
                ss().user = auth.sign_up(e2.strip(), p2)
                st.rerun()
            except auth.AuthError as err:
                st.error(str(err))


def _split_uploads(files):
    texts, parts = [], []
    for up in files or []:
        kind, val = classify_upload(up.name, up.getvalue())
        if kind == "text":
            texts.append(f"--- {up.name} ---\n{val}")
        else:
            parts.append(val)
    return texts, parts


def build_rubric_now(question_docs, rubric_docs, notes):
    q_texts, q_parts = _split_uploads(question_docs)
    r_texts, r_parts = _split_uploads(rubric_docs)
    blocks = []
    if q_texts:
        blocks.append("EXAM QUESTIONS — exactly what students were asked and answered. Build one "
                      "rubric entry per question listed here:\n" + "\n\n".join(q_texts))
    if r_texts:
        blocks.append("MARKING SCHEME / RUBRIC — use this for max marks, per-criterion breakdown, and "
                      "the marking policy. Where its wording differs from the questions above, the "
                      "QUESTIONS define what was asked:\n" + "\n\n".join(r_texts))
    if notes and notes.strip():
        blocks.append("ADDITIONAL TEACHER NOTES (secondary):\n" + notes.strip())
    guidelines = "\n\n".join(blocks) or None
    return setup_rubric(ss().batch_id, ss().batch_name, guidelines=guidelines,
                        answer_key_parts=(q_parts + r_parts) or None, uid=current_uid())


# --------------------------------------------------------------------------- #
# sidebar                                                                      #
# --------------------------------------------------------------------------- #
s = ss()

# Auth gate: when Firebase is configured, require sign-in. Otherwise run in local single-user mode.
if auth.auth_enabled() and not s.user:
    render_login()
    st.stop()

with st.sidebar:
    st.markdown("## 📝 GradePanel")
    st.caption(f"Signed in as **{display_email()}**")
    if s.user and st.button("Log out"):
        s.user = None
        go_home()
        st.rerun()
    st.divider()
    if s.step != "home":
        if s.batch_name:
            st.markdown(f"**{s.batch_name}**")
        flow = [("foundation", "Foundation"), ("documents", "Documents"), ("results", "Results")]
        keys = [k for k, _ in flow]
        cur = keys.index(s.step) if s.step in keys else 0
        for i, (k, label) in enumerate(flow):
            st.markdown(f"{'🟢' if i < cur else ('🔵' if i == cur else '⚪')} {label}")
        st.divider()
        if st.button("🏠 Home"):
            go_home()
            st.rerun()


# --------------------------------------------------------------------------- #
# HOME — greeting + past batches                                               #
# --------------------------------------------------------------------------- #
if s.step == "home":
    batches = list_batches(current_uid())
    st.title("📝 GradePanel")

    if not batches:
        # ---- new user ----
        st.header("👋 Hello!")
        st.caption(f"Signed in as {display_email()}")
        st.markdown(
            "**GradePanel grades handwritten exam answer sheets for you.** Upload a marking scheme "
            "and your students' scanned answers — an examiner panel of AI agents reads the "
            "handwriting and grades each question against your rubric, showing its reasoning and a "
            "confidence level, and flagging anything it can't read confidently for you to review. "
            "You stay in control: edit any score, then export the gradebook to a spreadsheet.")
        st.markdown("#### Your first steps")
        st.markdown(
            "1. **Set up the foundation** — pick your subject and name the exam session.\n"
            "2. **Add documents** — rubric, exam (question) paper, and each student's answer sheet.\n"
            "3. **Grade & review** — one click grades the batch; you review, edit, and export.")
        if st.button("🚀 Set up your foundation", type="primary"):
            s.step = "foundation"
            st.rerun()
    else:
        # ---- returning user: dashboard of past batches ----
        st.header("👋 Welcome back!")
        st.caption(f"Signed in as {display_email()}")
        total_students = sum(b["n_students"] for b in batches)
        k1, k2, k3 = st.columns(3)
        k1.metric("Batches", len(batches))
        k2.metric("Students graded", total_students)
        k3.metric("Open flags", sum(b["flags"] for b in batches))

        if st.button("➕ New grading session", type="primary"):
            s.step = "foundation"
            st.rerun()

        st.markdown("### Your batches")
        for b in batches:
            with st.container(border=True):
                c = st.columns([4, 2, 2, 2])
                c[0].markdown(f"**{b['name']}**  \n{b['subject']} · {b['session']}  \n_{b['created']}_")
                c[1].markdown(f"👥 {b['n_students']} student(s)")
                avg_txt = f"{b['avg']:.1f}/{b['total_marks']:g}" if b["total_marks"] else f"{b['avg']:.1f}"
                c[2].markdown(f"📊 Avg {avg_txt}  \n🚩 {b['flags']} flag(s)")
                if c[3].button("Open ➜", key=f"open_{b['batch_id']}"):
                    open_batch(b["batch_id"])
                    st.rerun()


# --------------------------------------------------------------------------- #
# FOUNDATION — subject + session, then Start Grading                           #
# --------------------------------------------------------------------------- #
elif s.step == "foundation":
    st.title("🧱 Set up the foundation")
    st.caption("Tell us what you're grading. This names the session you're about to create.")

    choice = st.selectbox("Primary subject", SUBJECTS, index=0)
    subject = st.text_input("Subject name", placeholder="e.g. English") if choice == "Other" else choice
    session = st.text_input("Exam session name", placeholder="e.g. Mid-term 2026")

    ready = bool(subject and subject.strip()) and bool(session.strip())
    col_a, col_b = st.columns([1, 4])
    if col_a.button("← Back"):
        go_home()
        st.rerun()
    if col_b.button("Start Grading ➜", type="primary", disabled=not ready):
        start_batch(subject.strip(), session.strip())
        st.rerun()


# --------------------------------------------------------------------------- #
# DOCUMENTS — rubric + exam sheet + answer sheets, then grade                  #
# --------------------------------------------------------------------------- #
elif s.step == "documents":
    st.title(f"📂 {s.batch_name}")
    st.caption("Attach the marking scheme, the exam (question) paper, and each student's answer sheet, "
               "then grade the batch.")

    left, right = st.columns(2, gap="large")

    with left:
        st.subheader("1 · Marking scheme")
        question_docs = st.file_uploader(
            "Exam sheet / question paper — what students were asked (Word, PDF, or image)",
            type=DOC_TYPES, accept_multiple_files=True, key="question_docs")
        rubric_docs = st.file_uploader(
            "Rubric / marking scheme — marks & criteria (Word, PDF, or image)",
            type=DOC_TYPES, accept_multiple_files=True, key="rubric_docs")
        notes = st.text_area(
            "Additional guidelines / notes — *secondary, optional*",
            placeholder="e.g. Be lenient on spelling for second-language learners. "
                        "Weight content 70% / examples 20% / language 10%.",
            height=120)
        if st.button("👁 Preview rubric",
                     disabled=not (question_docs or rubric_docs or notes.strip())):
            with st.spinner("Rubric Architect structuring the marking scheme..."):
                s.rubric = build_rubric_now(question_docs, rubric_docs, notes)
            st.success(f"Rubric: {len(s.rubric.questions)} questions, {s.rubric.total_marks:g} marks.")
        if s.rubric:
            for q in s.rubric.questions:
                with st.expander(f"Q{q.number} — {q.max_marks:g} marks"):
                    st.markdown(f"**Model answer:** {q.model_answer}")
                    for kp in q.key_points:
                        st.markdown(f"- {kp}")

    with right:
        st.subheader("2 · Answer sheets")
        st.caption("MVP: one student at a time. Upload ALL pages for the student (multiple images or "
                   "one PDF), then add.")
        sid = st.text_input("Student ID", value=f"student_{len(s.staged) + 1}", key="new_sid")
        pages = st.file_uploader("Answer sheet pages for this student", type=SHEET_TYPES,
                                 accept_multiple_files=True, key=f"pages_{s.uploader_key}")
        a, b = st.columns(2)
        if a.button("➕ Add student", disabled=not (pages and sid)):
            s.staged.append({"id": sid, "parts": [uploaded_to_part(f) for f in pages],
                             "files": [f.name for f in pages]})
            s.uploader_key += 1
            st.rerun()
        if b.button("🗑️ Clear", disabled=not s.staged):
            s.staged = []
            st.rerun()
        if s.staged:
            st.write(f"**{len(s.staged)} student(s) staged:**")
            for item in s.staged:
                st.write(f"- **{item['id']}** — {len(item['parts'])} page(s)")

    st.divider()
    have_scheme = bool(question_docs or rubric_docs or notes.strip() or s.rubric)
    ready = have_scheme and bool(s.staged)
    if not ready:
        st.info("Add a question paper / rubric **and** at least one student to enable grading.")
    if st.button("🚀 Grade batch", type="primary", disabled=not ready, use_container_width=True):
        with st.status("Grading batch…", expanded=True) as status:
            if s.rubric is None:
                st.write("🛠️ Rubric Architect structuring the marking scheme…")
                s.rubric = build_rubric_now(question_docs, rubric_docs, notes)
            st.write(f"✓ Rubric ready — {len(s.rubric.questions)} questions, {s.rubric.total_marks:g} marks")
            n = len(s.staged)
            for i, item in enumerate(s.staged, start=1):
                st.write(f"✍️ Grading **{item['id']}** ({i}/{n}) — reading handwriting + scoring…")
                grade_student(s.batch_id, StudentSheet(student_id=item["id"], parts=item["parts"]),
                              uid=current_uid())
            status.update(label=f"Graded {n} student(s).", state="complete")
        s.staged = []
        s.step = "results"
        st.rerun()


# --------------------------------------------------------------------------- #
# RESULTS — review/edit + dashboard                                            #
# --------------------------------------------------------------------------- #
elif s.step == "results":
    results = mem().load_results()
    summaries = mem().load_summaries()
    if s.rubric is None:
        s.rubric = mem().load_rubric()

    st.title(f"✅ {s.batch_name}")
    st.caption(f"{s.subject} · {s.session}")
    if st.button("➕ Add / grade more students"):
        s.step = "documents"
        st.rerun()

    tab_review, tab_dash = st.tabs(["Review & edit", "Dashboard"])

    with tab_review:
        if not results:
            st.info("No graded students yet.")
        else:
            sid = st.selectbox("Student", list(results.keys()))
            result = results[sid]
            m1, m2 = st.columns(2)
            m1.metric("Total (excl. flagged)", f"{result.total_awarded:g} / {result.total_max:g}")
            m2.metric("Flagged for review", len(result.open_flags))
            if sid in summaries:
                st.info(f"**Summary:** {summaries[sid].summary}\n\n**Feedback:** {summaries[sid].feedback}")
            st.divider()
            for a in result.answers:
                head = f"Q{a.number} — {a.awarded_marks:g}/{a.max_marks:g} · {CONF_BADGE.get(a.confidence, a.confidence)}"
                if a.flagged:
                    head = f"🚩 {head} · FLAGGED ({a.flag_reason})"
                with st.expander(head, expanded=a.flagged):
                    st.markdown(f"**Transcribed answer:** {a.transcribed_answer or '_(none read)_'}")
                    st.markdown(f"**AI reasoning:** {a.reasoning}")
                    col_a, col_b = st.columns([3, 1])
                    new = col_a.number_input(
                        f"Awarded marks for Q{a.number}", min_value=0.0, max_value=float(a.max_marks),
                        value=float(a.awarded_marks), step=0.5, key=f"score_{sid}_{a.number}")
                    if col_b.button("💾 Save", key=f"save_{sid}_{a.number}"):
                        mem().edit_score(sid, a.number, new, by="teacher")
                        st.success(f"Q{a.number} set to {new:g}. Flag cleared.")
                        st.rerun()
                    if a.flagged:
                        st.markdown("**🔁 Or clarify and let the AI re-grade this one:**")
                        hint = st.text_input("Clarification for the AI",
                                             placeholder="e.g. 'the smudged word is photosynthesis'",
                                             key=f"hint_{sid}_{a.number}")
                        if st.button("Re-grade with clarification", key=f"regrade_{sid}_{a.number}"):
                            with st.spinner("Re-grading just this answer…"):
                                regrade_flagged(s.batch_id, sid, a.number, hint, uid=current_uid())
                            st.success(f"Q{a.number} re-graded.")
                            st.rerun()

    with tab_dash:
        if not results or not s.rubric:
            st.info("Grade some students to populate the dashboard.")
        else:
            rows = []
            for sid, r in results.items():
                by_q = {a.number: a for a in r.answers}
                row = {"Student": sid}
                for q in s.rubric.questions:
                    a = by_q.get(q.number)
                    row[f"Q{q.number}"] = "FLAG" if (a and a.flagged) else (a.awarded_marks if a else None)
                row["Total"] = r.total_awarded
                row["Max"] = r.total_max
                row["Flags"] = len(r.open_flags)
                rows.append(row)
            df = pd.DataFrame(rows)

            k1, k2, k3 = st.columns(3)
            k1.metric("Students", len(results))
            k2.metric("Class average", f"{df['Total'].mean():.1f} / {s.rubric.total_marks:g}")
            k3.metric("Open flags", int(df["Flags"].sum()))
            st.dataframe(df, use_container_width=True, hide_index=True)

            from core.export import to_csv_bytes, to_xlsx_bytes
            d1, d2 = st.columns(2)
            d1.download_button("⬇️ Export XLSX", to_xlsx_bytes(s.rubric, results),
                               file_name=f"{s.batch_id}_grades.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            d2.download_button("⬇️ Export CSV", to_csv_bytes(s.rubric, results),
                               file_name=f"{s.batch_id}_grades.csv", mime="text/csv")
