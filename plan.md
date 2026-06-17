# Build plan & status

Grading engine first — accuracy is the make-or-break risk, so we de-risk it before any UI.
Commit at every phase; judges read the git log.

## Locked technical decisions
- Python + Streamlit. Vision-LLM reads handwriting AND grades in ONE call (no separate OCR).
- One thin provider-agnostic wrapper (`core/llm.py`); default Gemini, swappable by env var only.
- Structured JSON per question. Local/file storage only. No auth, no cloud DB.
- 3-agent panel (Architect / Grader / Summarizer) over append-only shared memory.
- Plain-Python orchestration — no heavy agent framework.

## Gemini SDK facts (confirmed before coding)
- Package `google-genai`: `from google import genai` / `from google.genai import types`.
- `client = genai.Client(api_key=...)`.
- Images/PDFs: `types.Part.from_bytes(data=..., mime_type="image/jpeg"|"application/pdf")`,
  interleaved with text in `contents=[...]`. Large PDFs → `client.files.upload(...)`.
- Structured JSON: `GenerateContentConfig(response_mime_type="application/json",
  response_schema=PydanticModel)`; pin exact field name against installed SDK at build time.
- Rubric caching (nice-to-have): `client.caches.create(...)` + `cached_content=cache.name`.
- Default model `gemini-2.5-flash`.

## Phases
- [ ] **Phase 0 — Scaffold + founding docs.** git init, docs, requirements, .env.example, stubs.
- [ ] **Phase 1 — Grading engine (NO UI).** llm wrapper + schemas + Architect + Grader, driven by
      `cli.py` on ONE real sample sheet. Prove handwriting read + grade + confidence + flags.
- [ ] **Phase 2 — Shared memory + agent panel.** Append-only ledger + precedent/consistency;
      wire Summarizer + orchestrator over a multi-student batch.
- [ ] **Phase 3 — Streamlit UI.** setup → upload → review/edit (reasoning + flags) → dashboard.
- [ ] **Phase 4 — Export + polish.** XLSX/CSV, image cleanup, demo data.
- [ ] **Phase 5 (stretch) — Flag → teacher clarifies → re-grade only flagged answers.**

## Out of scope today
login/auth, cloud DB, mobile app, essay grading, analytics.

## Open items / needs from teammate
- [ ] Free Gemini API key in `.env`.
- [ ] Sample answer key + at least one student sheet in `data/samples/`.
