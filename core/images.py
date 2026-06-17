"""Light image cleanup before the vision call: contrast + downscale (Pillow). No OCR.

Goal is cost/speed and legibility, NOT text extraction — the vision model reads the
handwriting itself. PDFs are passed straight through (Gemini reads multi-page PDFs natively).
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Union

from PIL import Image, ImageOps

from core.llm import ImagePart

MAX_EDGE = 2000  # downscale longest edge to this (plenty for handwriting, cheaper tokens)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def load_part(path: Union[str, Path]) -> ImagePart:
    """Load a sheet page from disk into an ImagePart, applying light cleanup to images."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        return ImagePart(data=path.read_bytes(), mime_type="application/pdf")
    if ext in IMAGE_EXTS:
        return prep_image(path.read_bytes())
    raise ValueError(f"Unsupported file type: {ext} ({path})")


def prep_image(raw: bytes) -> ImagePart:
    """Auto-orient, boost contrast, downscale, re-encode as JPEG."""
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)          # respect camera rotation
    img = img.convert("RGB")
    img = ImageOps.autocontrast(img, cutoff=1)  # lift faint pencil / uneven lighting
    w, h = img.size
    if max(w, h) > MAX_EDGE:
        scale = MAX_EDGE / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return ImagePart(data=out.getvalue(), mime_type="image/jpeg")
