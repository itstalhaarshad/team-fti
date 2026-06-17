"""Shared memory store — persistent, append-only, auditable, file-backed (data/batches/<id>/).

Holds: rubric, precedent/consistency ledger (jsonl), results, flags, summaries, audit log.
The precedent ledger is the core product value: same answer -> same marks across students.

TODO(phase2): implement Memory(batch_id) with read/append helpers + audit logging.
"""
