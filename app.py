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
    guidelines = st.text_area(
        "Marking guidelines (free text)",
        placeholder="Q1 (5 marks): Define photosynthesis. Key points: sunlight, CO2+water; "
                    "glucose+oxygen; chloroplast/chlorophyll.\nQ2 (5 marks): ...",
        height=160,
    )
    key_files = st.file_uploader(
        "Model / sample answer sheet (optional — image or PDF)",
        type=["jpg", "jpeg", "png", "webp", "pdf"], accept_multiple_files=True)

    if st.button("🛠️ Build rubric", type="primary"):
        if not guidelines.strip() and not key_files:
            st.error("Provide guidelines text and/or a model answer sheet.")
        else:
            with st.spinner("Rubric Architect is structuring the marking scheme..."):
                key_parts = [uploaded_to_part(f) for f in key_files] if key_files else None
                s.rubric = setup_rubric(s.batch_id, s.title,
                                        guidelines=guidelines or None,
                                        answer_key_parts=key_parts)
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
        st.subheader("Upload student answer sheets")
        st.caption("Each uploaded file = one student (id taken from the filename). "
                   "Multi-page students: combine pages into a single PDF.")
        sheets_files = st.file_uploader(
            "Student sheets (images or PDFs)",
            type=["jpg", "jpeg", "png", "webp", "pdf"], accept_multiple_files=True,
            key="student_files")

        if sheets_files:
            st.write(f"**{len(sheets_files)} sheet(s) staged:** " +
                     ", ".join(f.name for f in sheets_files))

        if st.button("🤖 Grade all sheets", type="primary", disabled=not sheets_files):
            progress = st.progress(0.0)
            status = st.empty()
            n = len(sheets_files)
            for i, f in enumerate(sheets_files, start=1):
                sid = f.name.rsplit(".", 1)[0]
                status.write(f"Grading **{sid}** ({i}/{n}) — reading handwriting + scoring...")
                sheet = StudentSheet(student_id=sid, parts=[uploaded_to_part(f)])
                grade_student(s.batch_id, sheet)  # persists to shared memory
                progress.progress(i / n)
            s.graded = True
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
