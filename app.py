"""GradePanel — Streamlit teacher UI.

Product flow: Create batch -> Add documents (rubric + student sheets) -> one click to grade
-> Results (review/edit + dashboard + export). Coordinates the 3-agent panel via
agents.orchestrator over the file-backed shared Memory.
"""
from __future__ import annotations

import re
import uuid

import pandas as pd
import streamlit as st

from agents.orchestrator import (StudentSheet, grade_student, regrade_flagged,
                                  setup_rubric)
from core.documents import classify_upload
from core.images import prep_image
from core.llm import ImagePart
from core.memory import Memory
from core.schemas import Confidence

st.set_page_config(page_title="GradePanel", page_icon="📝", layout="wide")

CONF_BADGE = {Confidence.high: "🟢 high", Confidence.medium: "🟡 medium", Confidence.low: "🔴 low"}
USER_EMAIL = "itstalhaarshad@gmail.com"
SHEET_TYPES = ["jpg", "jpeg", "png", "webp", "pdf"]
DOC_TYPES = ["docx", "txt", "pdf", "jpg", "jpeg", "png", "webp"]


# --------------------------------------------------------------------------- #
# state                                                                        #
# --------------------------------------------------------------------------- #
def ss():
    s = st.session_state
    s.setdefault("step", "create")        # create -> documents -> results
    s.setdefault("batch_id", None)
    s.setdefault("batch_name", "")
    s.setdefault("rubric", None)
    s.setdefault("staged", [])            # [{id, parts, files}]
    s.setdefault("uploader_key", 0)
    return s


def mem():
    return Memory(ss().batch_id)


def uploaded_to_part(up) -> ImagePart:
    data = up.getvalue()
    if up.type == "application/pdf" or up.name.lower().endswith(".pdf"):
        return ImagePart(data=data, mime_type="application/pdf")
    return prep_image(data)


def new_batch(name: str):
    s = ss()
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "batch"
    s.batch_id = f"{slug}-{uuid.uuid4().hex[:6]}"
    s.batch_name = name
    s.rubric = None
    s.staged = []
    s.step = "documents"


def build_rubric_now(rubric_docs, notes):
    text_blocks, key_parts = [], []
    for up in rubric_docs or []:
        kind, val = classify_upload(up.name, up.getvalue())
        (text_blocks if kind == "text" else key_parts).append(
            f"--- {up.name} ---\n{val}" if kind == "text" else val)
    blocks = []
    if text_blocks:
        blocks.append("PRIMARY — MARKING SCHEME / RUBRIC DOCUMENT(S):\n" + "\n\n".join(text_blocks))
    if notes and notes.strip():
        blocks.append("SECONDARY — ADDITIONAL TEACHER NOTES:\n" + notes.strip())
    guidelines = "\n\n".join(blocks) or None
    return setup_rubric(ss().batch_id, ss().batch_name, guidelines=guidelines,
                        answer_key_parts=key_parts or None)


# --------------------------------------------------------------------------- #
# sidebar                                                                      #
# --------------------------------------------------------------------------- #
s = ss()
STEPS = [("create", "Create batch"), ("documents", "Add documents"), ("results", "Results")]
with st.sidebar:
    st.markdown("## 📝 GradePanel")
    st.caption(f"Signed in as **{USER_EMAIL}**")
    st.divider()
    if s.batch_name:
        st.markdown(f"**Batch:** {s.batch_name}")
    cur = [k for k, _ in STEPS].index(s.step)
    for i, (key, label) in enumerate(STEPS):
        mark = "🟢" if i < cur else ("🔵" if i == cur else "⚪")
        st.markdown(f"{mark} {label}")
    st.divider()
    if s.batch_name and st.button("➕ New batch"):
        s.step, s.batch_id, s.batch_name, s.rubric, s.staged = "create", None, "", None, []
        st.rerun()


# --------------------------------------------------------------------------- #
# STEP 1 — create batch                                                        #
# --------------------------------------------------------------------------- #
if s.step == "create":
    st.title("📝 GradePanel")
    st.subheader("Create a grading batch")
    st.caption("A batch = one class/exam you're grading (rubric + all student sheets).")
    name = st.text_input("Batch name", placeholder="e.g. Functional English 1 2026")
    if st.button("Create batch ➜", type="primary", disabled=not name.strip()):
        new_batch(name.strip())
        st.rerun()


# --------------------------------------------------------------------------- #
# STEP 2 — add documents, then grade                                           #
# --------------------------------------------------------------------------- #
elif s.step == "documents":
    st.title(f"📂 {s.batch_name}")
    st.caption("Add the marking scheme and the student answer sheets, then grade the whole batch.")

    left, right = st.columns(2, gap="large")

    # --- marking scheme ---
    with left:
        st.subheader("1 · Marking scheme")
        rubric_docs = st.file_uploader(
            "Rubric document — **primary** (Word, PDF, or image). Add the questions paper too if you like.",
            type=DOC_TYPES, accept_multiple_files=True, key="rubric_docs")
        notes = st.text_area(
            "Additional guidelines / notes — *secondary, optional*",
            placeholder="e.g. Be lenient on spelling for second-language learners. "
                        "Weight content 70% / examples 20% / language 10%.",
            height=140)
        if st.button("👁 Preview rubric", disabled=not (rubric_docs or notes.strip())):
            with st.spinner("Rubric Architect structuring the marking scheme..."):
                s.rubric = build_rubric_now(rubric_docs, notes)
            st.success(f"Rubric: {len(s.rubric.questions)} questions, {s.rubric.total_marks:g} marks.")
        if s.rubric:
            for q in s.rubric.questions:
                with st.expander(f"Q{q.number} — {q.max_marks:g} marks"):
                    st.markdown(f"**Model answer:** {q.model_answer}")
                    for kp in q.key_points:
                        st.markdown(f"- {kp}")

    # --- students ---
    with right:
        st.subheader("2 · Student answer sheets")
        st.caption("Upload ALL pages for one student together (multiple images or one PDF), then add.")
        sid = st.text_input("Student ID", value=f"student_{len(s.staged) + 1}", key="new_sid")
        pages = st.file_uploader("Pages for this student", type=SHEET_TYPES,
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

    # --- the one grade button ---
    st.divider()
    have_scheme = bool(st.session_state.get("rubric_docs") or notes.strip() or s.rubric)
    ready = have_scheme and bool(s.staged)
    if not ready:
        st.info("Add a marking scheme **and** at least one student to enable grading.")
    if st.button("🚀 Grade batch", type="primary", disabled=not ready, use_container_width=True):
        with st.status("Grading batch…", expanded=True) as status:
            if s.rubric is None:
                st.write("🛠️ Rubric Architect structuring the marking scheme…")
                s.rubric = build_rubric_now(st.session_state.get("rubric_docs"), notes)
            st.write(f"✓ Rubric ready — {len(s.rubric.questions)} questions, {s.rubric.total_marks:g} marks")
            n = len(s.staged)
            for i, item in enumerate(s.staged, start=1):
                st.write(f"✍️ Grading **{item['id']}** ({i}/{n}) — reading handwriting + scoring…")
                grade_student(s.batch_id, StudentSheet(student_id=item["id"], parts=item["parts"]))
            status.update(label=f"Graded {n} student(s).", state="complete")
        s.staged = []
        s.step = "results"
        st.rerun()


# --------------------------------------------------------------------------- #
# STEP 3 — results (review + dashboard)                                        #
# --------------------------------------------------------------------------- #
elif s.step == "results":
    results = mem().load_results()
    summaries = mem().load_summaries()
    if s.rubric is None:
        s.rubric = mem().load_rubric()

    st.title(f"✅ {s.batch_name} — results")
    c1, c2 = st.columns([1, 1])
    if c1.button("➕ Add / grade more students"):
        s.step = "documents"
        st.rerun()

    tab_review, tab_dash = st.tabs(["Review & edit", "Dashboard"])

    # ---- review & edit ----
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
                                regrade_flagged(s.batch_id, sid, a.number, hint)
                            st.success(f"Q{a.number} re-graded.")
                            st.rerun()

    # ---- dashboard ----
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
