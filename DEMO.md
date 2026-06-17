# GradePanel — demo script

A tight, repeatable run for judges. ~4 minutes. Practice it once end-to-end before presenting.

## 30-second pitch
> Teachers spend hours grading handwritten answer sheets — slow, inconsistent, no feedback for
> students. **GradePanel** reads the handwriting **and** grades it against the teacher's own rubric in
> a single AI pass: per-question marks, the reasoning behind them, and a confidence level. Anything it
> can't read confidently it **flags** instead of guessing. The teacher reviews, edits, and exports — in
> minutes, not hours. Under the hood it's a 3-agent examiner panel with a shared consistency ledger so
> the same answer earns the same mark across every student.

## Before you present (checklist)
- [ ] App running: `streamlit run app.py` → http://localhost:8501 (or your deployed URL).
- [ ] You're **logged out** (so judges see the sign-in screen).
- [ ] Demo safety net seeded: `python scripts/seed_demo.py` → login `demo@gradepanel.app` / `demo123456`.
- [ ] Have one real student's answer-sheet pages ready to upload (or a PDF).
- [ ] Internet up (Gemini + Firebase are live calls).

## Primary flow (do this live)
1. **Sign in / Create account** — show the email gate. Create a fresh account on the spot (proves real auth).
2. **Hello screen** — point out the brief + "first steps" for a new teacher.
3. **Set up the foundation** — pick subject **English**, session **Mid-term 2026** → **Start Grading**.
4. **Documents** —
   - Upload the **question paper** and the **rubric** (`.docx`/PDF/image).
   - Click **👁 Preview rubric** → show it built a structured rubric (4 questions, 50 marks) from the
     teacher's own documents — *the "Rubric Architect" agent*.
   - **Answer sheets** — add a student, upload all their pages, **➕ Add student** (mention you can stage a
     whole class this way), then **🚀 Grade batch**.
5. **Watch the status log** — "Rubric ready… Grading student_1…" (the agent panel running).
6. **Review & edit** — open a question:
   - Show the **transcription** (it read the cursive), the **reasoning**, the **confidence** badge.
   - Find a **🚩 flagged** answer → type a clarification → **Re-grade** → it updates. *(Teacher-in-the-loop.)*
   - Edit a score by hand → it saves (every edit is audited).
7. **Dashboard** — class table, average, flag count → **Export XLSX**. Open the file. Done.

## If anything flops (safety net)
Log out → sign in as **`demo@gradepanel.app` / `demo123456`** → open the seeded batch
**"Functional English — Final-term 2026"** (3 students, one flagged answer). Everything below works
offline-of-Gemini because it's already graded and stored in Firestore.

## Differentiators to say out loud
- **One vision pass**, no separate OCR — keeps visual context, grades messy handwriting better.
- **Flags instead of guessing** — trust: it never invents a mark it isn't sure of.
- **Consistency ledger** — append-only precedents so identical answers get identical marks across 30 students.
- **Real product plumbing** — email auth + Firestore per-teacher storage + spreadsheet export, not a mock.
- **Provider-agnostic** — swap Gemini → Claude/OpenAI by changing one env var.

## If a judge probes limitations (be honest)
- AI marks a touch **stricter** than a human — by design the **teacher edits**; we keep them in the loop.
- Validated on a few students, not yet a full class of 30 at once (cost/latency at scale is next).
- Single grader today; a second "moderator" agent pass is a natural next step.
