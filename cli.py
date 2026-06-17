"""Phase-1 de-risk harness: grade student sheet(s) end-to-end and print JSON. No UI.

Examples:
    python cli.py --title "10th English" --answer-key data/samples/key.jpg \
        --student alice data/samples/alice_p1.jpg data/samples/alice_p2.jpg

    python cli.py --title "10th English" --guidelines "Q1: photosynthesis... (5 marks)" \
        --student bob data/samples/bob.jpg

Proves the engine (read handwriting + grade + confidence + flags + consistency) before any UI.
Use --student multiple times for several students in one batch (exercises the precedent ledger).
"""
from __future__ import annotations

import argparse
import json
import sys

from agents.orchestrator import StudentSheet, run_batch
from core.images import load_part


def main() -> int:
    ap = argparse.ArgumentParser(description="Grade answer sheets via the 3-agent panel (no UI).")
    ap.add_argument("--batch-id", default="cli-batch")
    ap.add_argument("--title", default="CLI batch")
    ap.add_argument("--guidelines", help="Free-text marking guidelines.")
    ap.add_argument("--answer-key", nargs="+", help="Model answer sheet image(s)/PDF.")
    ap.add_argument("--student", nargs="+", action="append", metavar=("ID", "FILE"),
                    help="Student id followed by one or more sheet files. Repeatable.")
    args = ap.parse_args()

    if not args.student:
        ap.error("at least one --student ID FILE [FILE ...] is required")
    if not args.guidelines and not args.answer_key:
        ap.error("provide --guidelines and/or --answer-key to build the rubric")

    answer_key_parts = [load_part(p) for p in args.answer_key] if args.answer_key else None
    sheets = []
    for entry in args.student:
        sid, files = entry[0], entry[1:]
        if not files:
            ap.error(f"--student {sid} needs at least one file")
        sheets.append(StudentSheet(student_id=sid, parts=[load_part(f) for f in files]))

    print(f"Grading {len(sheets)} student(s) for batch '{args.title}'...\n", file=sys.stderr)
    view = run_batch(args.batch_id, args.title,
                     sheets=sheets, guidelines=args.guidelines,
                     answer_key_parts=answer_key_parts)

    print("===== RUBRIC =====")
    print(view.rubric.model_dump_json(indent=2))
    for sid, result in view.results.items():
        print(f"\n===== STUDENT {sid}: {result.total_awarded}/{result.total_max} "
              f"({len(result.open_flags)} flagged) =====")
        print(result.model_dump_json(indent=2))
        print("--- summary ---")
        print(view.summaries[sid].model_dump_json(indent=2))
    print(f"\nBatch open flags: {view.total_open_flags}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
