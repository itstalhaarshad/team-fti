"""Phase-1 de-risk harness: grade ONE sheet end-to-end and print JSON. No UI.

Usage:
    python cli.py --rubric data/samples/answer_key.jpg --sheet data/samples/student1.jpg
    python cli.py --guidelines "Q1: photosynthesis ... (5 marks)" --sheet data/samples/student1.jpg

Proves the grading engine (read handwriting + grade + confidence + flags) before any UI.

TODO(phase1): wire Architect -> Grader and pretty-print the StudentResult JSON.
"""
