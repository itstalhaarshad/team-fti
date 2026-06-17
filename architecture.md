# Architecture — 3-agent examiner panel + shared memory

We model grading as a small panel of specialist agents coordinating through one shared,
append-only memory store — not a single monolithic prompt. Each agent calls our own thin
vision/LLM wrapper (`core/llm.py`) as its only tool. Orchestration is plain Python.

```
                         ┌────────────────────────────────────────┐
                         │           SHARED MEMORY (memory.py)     │
                         │  append-only, auditable, file-backed    │
                         │                                         │
  sample sheet  ──┐      │  • rubric         (per-question model   │
  + guidelines    │      │                    answer + max marks)  │
                  ▼      │  • precedent ledger  ◄── CORE VALUE      │
        ┌───────────────┐│      answer-pattern → marks awarded     │
        │ 1. Rubric     ││  • flags          (needs teacher)       │
        │    Architect  │┼─►  • results        (per question)      │
        │  (once/batch) ││  • summaries      (per student)         │
        └───────────────┘│  • audit log      (every write, append)│
                         └───────────────▲────────────────────────┘
  student sheet ──┐                      │ read rubric + precedents
                  ▼                      │ write result + precedent + flags
        ┌───────────────┐                │
        │ 2. Grader /   │────────────────┘
        │  First Marker │  grades CONFIDENT answers vs rubric;
        │  (per sheet)  │  writes a precedent per graded answer;
        └───────┬───────┘  FLAGS low-confidence/unreadable — never guesses
                ▼
        ┌───────────────┐
        │ 3. Summarizer │  short per-student summary + feedback +
        │  (per sheet)  │  list of items still pending teacher review
        └───────────────┘
```

## Agents
### 1. Rubric Architect — runs once per batch
- **In:** sample answer image and/or free-text guidelines, total questions/marks if known.
- **Out:** structured `Rubric` (list of `QuestionRubric`: number, model answer, max marks,
  optional key points) written to shared memory.
- **Why an agent:** normalizes messy teacher input into the one contract every Grader call depends on.

### 2. Grader / First Marker — per student sheet
- **In:** student sheet image(s) + the rubric + **relevant precedents** from the ledger.
- **Out:** per question → awarded marks, max marks, reasoning, confidence (`high|medium|low`).
  - Confident → grade it, and append a **precedent** (answer fingerprint → marks + reason).
  - Low-confidence / unreadable → **flag** it (reason: unreadable / ambiguous / off-rubric); do NOT grade.
- **Consistency:** before finalizing a mark, the Grader is shown prior precedents for the same
  question so equivalent answers converge on the same score across students.

### 3. Summarizer — per student sheet
- **In:** that student's graded results + flags.
- **Out:** short summary, actionable feedback, total awarded/total max, pending-review list.

## Shared memory (memory.py) — the core product value
A persistent, **append-only** per-batch store (JSON files under `data/batches/<batch_id>/`):
- `rubric.json` — written once by the Architect.
- `ledger.jsonl` — **precedent/consistency ledger**, append-only: each line = one graded answer
  (question, answer fingerprint, marks, reason, source student). This is what makes the same
  answer earn the same mark across all 30 students, and it's fully auditable.
- `results.json` — per-student, per-question results (mutable via teacher edits, but every edit
  is also appended to the audit log).
- `flags.json` — open items awaiting teacher clarification.
- `summaries.json` — per-student summaries.
- `audit.jsonl` — append-only log of every write (who/what/when-ish), so judges can trace decisions.

## Provider-agnostic wrapper (llm.py)
Single surface the agents use:
- `generate_json(parts, schema, system=None, cache=None) -> dict` — vision+text in, validated JSON out.
- Provider + model chosen from env (`LLM_PROVIDER`, `LLM_MODEL`). Default Gemini; Claude/OpenAI
  behind the same function signature. Nothing else in the app imports a vendor SDK.

## Orchestration
`agents/orchestrator.py`:
1. Architect once → rubric in memory.
2. For each student sheet (sequential, asyncio-ready): Grader → Summarizer, reading/writing memory.
3. Return a batch view (all students + totals + open flags) for the dashboard.

Stretch loop: teacher answers a flag → re-run Grader for only that question with the clarification
added to context → update result + append precedent.
