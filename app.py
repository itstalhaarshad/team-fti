"""GradePanel — Streamlit teacher UI.

Tabs: Setup (build rubric) -> Upload & Grade -> Review & Edit -> Dashboard (+ export).
Coordinates the 3-agent panel via agents.orchestrator over the file-backed shared Memory.
"""
from __future__ import annotations

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


# --------------------------------------------------------------------------- #
# session state                                                                #
# --------------------------------------------------------------------------- #
def ss():
    s = st.session_state
    s.setdefault("batch_id", "batch-" + uuid.uuid4().hex[:8])
    s.setdefault("title", "10th Grade — English")
    s.setdefault("rubric", None)
    s.setdefault("graded", False)
    s.setdefault("staged", [])        # students queued for grading: [{id, parts, files}]
    s.setdefault("uploader_key", 0)   # bump to reset the page uploader after each add
    return s


def uploaded_to_part(up) -> ImagePart:
    """Convert a Streamlit UploadedFile to an ImagePart (cleanup images, pass PDFs through)."""
    data = up.getvalue()
    if up.type == "application/pdf" or up.name.lower().endswith(".pdf"):
        return ImagePart(data=data, mime_type="application/pdf")
    return prep_image(data)


def mem() -> Memory:
    return Memory(ss().batch_id)


# --------------------------------------------------------------------------- #
# header                                                                        #
# --------------------------------------------------------------------------- #
s = ss()
st.title("📝 GradePanel")
st.caption("Agentic grading for handwritten answer sheets — reads + grades in one vision pass, "
           "flags what it can't read, keeps marks consistent across students.")

tab_setup, tab_upload, tab_review, tab_dash = st.tabs(
    ["① Setup rubric", "② Upload & grade", "③ Review & edit", "④ Dashboard"])


# --------------------------------------------------------------------------- #
# ① Setup                                                                       #
# --------------------------------------------------------------------------- #
with tab_setup:
    st.subheader("Marking scheme")
    s.title = st.text_input("Batch title", s.title)

    st.markdown("**① Rubric / marking-scheme document — _primary_**")
    rubric_docs = st.file_uploader(
        "Upload the rubric (Word .docx, PDF, or image). You can also add the questions paper here.",
        type=["docx", "txt", "pdf", "jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True, key="rubric_docs")

    st.markdown("**② Additional guidelines / notes — _secondary, optional_**")
    notes = st.text_area(
        "Anything to add on top of the document (leniency, context, the actual question wording, …)",
        placeholder="e.g. Be lenient on spelling for second-language learners. "
                    "Weight content 70% / examples 20% / language 10%.",
        height=120)

    if st.button("🛠️ Build rubric", type="primary"):
        if not rubric_docs and not notes.strip():
            st.error("Upload a rubric document and/or add notes.")
        else:
            text_blocks, key_parts = [], []
            for up in rubric_docs or []:
                kind, val = classify_upload(up.name, up.getvalue())
                if kind == "text":
                    text_blocks.append(f"--- {up.name} ---\n{val}")
                else:
                    key_parts.append(val)
            blocks = []
            if text_blocks:
                blocks.append("PRIMARY — MARKING SCHEME / RUBRIC DOCUMENT(S):\n" + "\n\n".join(text_blocks))
            if notes.strip():
                blocks.append("SECONDARY — ADDITIONAL TEACHER NOTES:\n" + notes.strip())
            guidelines = "\n\n".join(blocks) or None
            with st.spinner("Rubric Architect is structuring the marking scheme..."):
                s.rubric = setup_rubric(s.batch_id, s.title, guidelines=guidelines,
                                        answer_key_parts=key_parts or None)
                s.graded = False
            st.success(f"Rubric built — {len(s.rubric.questions)} questions, "
                       f"{s.rubric.total_marks:g} total marks.")

    if s.rubric:
        st.divider()
        st.subheader(f"Rubric · {s.rubric.title}")
        for q in s.rubric.questions:
            with st.expander(f"Q{q.number} — {q.max_marks:g} marks"):
                st.markdown(f"**Model answer:** {q.model_answer}")
                if q.key_points:
                    st.markdown("**Key points:**")
                    for kp in q.key_points:
                        st.markdown(f"- {kp}")


# --------------------------------------------------------------------------- #
# ② Upload & grade                                                              #
# --------------------------------------------------------------------------- #
with tab_upload:
    if not s.rubric:
        st.info("Build the rubric in tab ① first.")
    else:
        st.subheader("Add a student")
        st.caption("Upload ALL pages for one student together (multiple images, or a single PDF), "
                   "give them an id, and add them to the batch. Repeat for each student.")
        sid = st.text_input("Student ID", value=f"student_{len(s.staged) + 1}", key="new_sid")
        pages = st.file_uploader(
            "Pages for this student (images or one PDF)",
            type=["jpg", "jpeg", "png", "webp", "pdf"], accept_multiple_files=True,
            key=f"pages_{s.uploader_key}")

        c1, c2 = st.columns(2)
        if c1.button("➕ Add student to batch", disabled=not (pages and sid)):
            s.staged.append({"id": sid, "parts": [uploaded_to_part(f) for f in pages],
                             "files": [f.name for f in pages]})
            s.uploader_key += 1  # reset the uploader for the next student
            st.rerun()
        if c2.button("🗑️ Clear staged", disabled=not s.staged):
            s.staged = []
            st.rerun()

        if s.staged:
            st.divider()
            st.write(f"**{len(s.staged)} student(s) staged:**")
            for item in s.staged:
                st.write(f"- **{item['id']}** — {len(item['parts'])} page(s)")

            if st.button("🤖 Grade staged students", type="primary"):
                progress = st.progress(0.0)
                status = st.empty()
                n = len(s.staged)
                for i, item in enumerate(s.staged, start=1):
                    status.write(f"Grading **{item['id']}** ({i}/{n}) — reading handwriting + scoring...")
                    grade_student(s.batch_id, StudentSheet(student_id=item["id"], parts=item["parts"]))
                    progress.progress(i / n)
                s.graded = True
                s.staged = []
                status.write("Done.")
                st.success(f"Graded {n} student(s). See tabs ③ and ④.")


# --------------------------------------------------------------------------- #
# ③ Review & edit                                                              #
# --------------------------------------------------------------------------- #
with tab_review:
    results = mem().load_results()
    summaries = mem().load_summaries()
    if not results:
        st.info("No graded sheets yet — grade some in tab ②.")
    else:
        sid = st.selectbox("Student", list(results.keys()))
        result = results[sid]
        flagged = len(result.open_flags)
        c1, c2 = st.columns(2)
        c1.metric("Total (excl. flagged)", f"{result.total_awarded:g} / {result.total_max:g}")
        c2.metric("Flagged for review", flagged)
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
                        with st.spinner("Re-grading just this answer..."):
                            regrade_flagged(s.batch_id, sid, a.number, hint)
                        st.success(f"Q{a.number} re-graded.")
                        st.rerun()


# --------------------------------------------------------------------------- #
# ④ Dashboard                                                                   #
# --------------------------------------------------------------------------- #
with tab_dash:
    results = mem().load_results()
    if not results or not s.rubric:
        st.info("Grade some sheets to populate the dashboard.")
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

        m1, m2, m3 = st.columns(3)
        m1.metric("Students", len(results))
        avg = df["Total"].mean() if len(df) else 0
        m2.metric("Class average", f"{avg:.1f} / {s.rubric.total_marks:g}")
        m3.metric("Open flags", int(df["Flags"].sum()))

        st.dataframe(df, use_container_width=True, hide_index=True)

        from core.export import to_csv_bytes, to_xlsx_bytes
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Export XLSX", to_xlsx_bytes(s.rubric, results),
                           file_name=f"{s.batch_id}_grades.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        d2.download_button("⬇️ Export CSV", to_csv_bytes(s.rubric, results),
                           file_name=f"{s.batch_id}_grades.csv", mime="text/csv")
