# GradePanel — agentic grading for handwritten answer sheets

An agentic AI app that reads handwritten exam answer sheets **and** grades them against a
teacher's rubric in a single vision pass — returning per-question marks, reasoning, and a
confidence level, while **flagging** anything it can't read confidently instead of guessing.

Built for teachers who grade ~30 papers per class by hand: slow, inconsistent, no feedback.

## What it does (demo flow)
1. **Set up a batch** — provide a model answer sheet (image) and/or free-text marking guidelines.
2. **Upload student sheets** — photos or PDFs (one student = one or more pages).
3. **AI grades each question** — reads handwriting + scores against the rubric in one pass:
   awarded marks, max marks, reasoning, confidence. Low-confidence answers are flagged, not guessed.
4. **Teacher reviews** — every question shown with the AI's reasoning; edit any score; finalize.
5. **Dashboard + export** — all students + totals, exported to XLSX/CSV.

## Architecture (the differentiator)
A lean **3-agent examiner panel** over a shared, append-only memory store — not one mega-prompt:
- **Rubric Architect** (once per batch) → structured rubric in shared memory.
- **Grader / First Marker** (per sheet) → grades confident answers, writes a **precedent** to the
  consistency ledger, flags the rest.
- **Summarizer** (per sheet) → per-student summary + feedback + pending-review list.

The **consistency ledger** (precedents: "this answer earned these marks") is the core product
value — it keeps the same answer earning the same mark across all 30 students. See `architecture.md`.

## Tech
- Python + Streamlit UI.
- Vision-LLM reads handwriting AND reasons in one call — **no separate OCR stage**.
- One thin, provider-agnostic wrapper (`core/llm.py`). Default = **Google Gemini** (free AI Studio
  key, vision + structured JSON). Swap to Claude/OpenAI by changing env vars only.
- Structured JSON output (provider schema mode). Local/in-memory + local-file storage. No auth, no cloud DB.

## Quick start
```bash
pip install -r requirements.txt
cp .env.example .env          # then put your free Gemini key in GEMINI_API_KEY
# Phase 1: prove the engine on one sheet, no UI:
python cli.py --rubric data/samples/answer_key.jpg --sheet data/samples/student1.jpg
# Full app:
streamlit run app.py
```

## Deploying (Streamlit Community Cloud)
The app deploys straight from GitHub — no code changes needed (keys are read from the
environment, and Cloud injects its secrets as env vars).

1. Push to GitHub: `git push origin main`.
2. Go to [share.streamlit.io](https://share.streamlit.io) → **Create app** → pick this repo,
   branch `main`, **Main file path** = `app.py`.
3. Under **Advanced settings**:
   - **Python version**: select 3.12 (set here, not via `runtime.txt` — Cloud ignores that).
   - **Secrets**: paste your config as TOML (this replaces your local `.env`):
     ```toml
     LLM_PROVIDER = "gemini"
     LLM_MODEL = "gemini-2.5-flash"
     GEMINI_API_KEY = "your-real-key-here"
     ENABLE_RUBRIC_CACHE = "false"
     ```
4. **Deploy.**

> ⚠️ Community Cloud has an **ephemeral filesystem**: the file-backed memory store under
> `data/batches/` is wiped whenever the app reboots or sleeps. Fine for a demo; move it to an
> external store for durable use.

## Status
See `plan.md` for the phased build order and live checklist.
