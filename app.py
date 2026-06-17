"""Streamlit entry point — tabs: Setup -> Upload -> Review/Edit -> Dashboard.

TODO(phase3): build the teacher-in-the-loop UI over the orchestrator + shared memory.
"""
import streamlit as st

st.set_page_config(page_title="GradePanel", layout="wide")
st.title("GradePanel")
st.info("UI lands in Phase 3. Grading engine is being proven via cli.py first.")
