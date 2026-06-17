"""Plain-Python orchestration of the 3-agent panel over a batch (sequential / asyncio-ready).

1. Rubric Architect once -> rubric in memory.
2. Per student sheet: Grader -> Summarizer, reading/writing shared memory.
3. Return a batch view (students + totals + open flags) for the dashboard.

TODO(phase2): run_batch(batch_id, rubric_inputs, student_sheets) -> BatchView.
"""
