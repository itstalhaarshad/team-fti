"""Light image cleanup before the vision call: deskew / contrast / downscale (Pillow).

Deliberately minimal — we do NOT run OCR. Goal is cost/speed, not text extraction.

TODO(phase1+): prep(path_or_bytes) -> (bytes, mime_type).
"""
