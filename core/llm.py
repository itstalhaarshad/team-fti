"""Thin, provider-agnostic LLM/vision wrapper — the ONLY place a vendor SDK is imported.

Public surface the agents use:
    generate_json(parts, schema, system=None) -> schema instance

`parts` is a list of either `str` (text) or `ImagePart` (image/PDF bytes + mime). The wrapper
routes to the provider named by env `LLM_PROVIDER` (default 'gemini'), using model `LLM_MODEL`,
and forces structured JSON conforming to `schema` (a Pydantic BaseModel subclass). It returns a
validated instance of `schema`.

Swapping providers = changing env vars only. Claude/OpenAI land behind the same signature; they
parse JSON text into `schema` the same way, so callers never change.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Type, TypeVar, Union

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

T = TypeVar("T", bound=BaseModel)


@dataclass
class ImagePart:
    """An image or PDF page(s) to send to the vision model."""
    data: bytes
    mime_type: str  # e.g. "image/jpeg", "image/png", "application/pdf"


Part = Union[str, ImagePart]


class LLMError(Exception):
    """A surfaced provider error. `status` is the HTTP status (int) when known."""
    def __init__(self, status, message: str):
        self.status = status
        self.message = message
        super().__init__(f"[{status}] {message}")


# statuses worth retrying (transient); everything else fails fast
_RETRYABLE = {429, 500, 502, 503, 504}


def _provider() -> str:
    return os.environ.get("LLM_PROVIDER", "gemini").strip().lower()


def _model() -> str:
    return os.environ.get("LLM_MODEL", "gemini-2.5-flash").strip()


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #
def generate_json(parts: List[Part], schema: Type[T], system: str | None = None,
                  *, max_retries: int = 2) -> T:
    """Send text+image parts, force structured JSON, return a validated `schema` instance."""
    provider = _provider()
    for attempt in range(max_retries + 1):
        try:
            if provider == "gemini":
                return _gemini_generate_json(parts, schema, system)
            if provider == "claude":
                return _claude_generate_json(parts, schema, system)
            if provider == "openai":
                return _openai_generate_json(parts, schema, system)
            raise ValueError(f"Unknown LLM_PROVIDER={provider!r} (expected gemini|claude|openai)")
        except LLMError as e:
            # only retry transient statuses; fail fast on 400/401/403/404 (retrying won't help)
            if e.status in _RETRYABLE and attempt < max_retries:
                time.sleep(min(3 * (2 ** attempt), 15))
                continue
            raise
        except Exception as e:  # parse hiccup etc. -> brief backoff + retry
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise


# --------------------------------------------------------------------------- #
# Gemini (default)                                                             #
# --------------------------------------------------------------------------- #
_gemini_client = None


_gemini_key = None


def _get_gemini_client():
    """Build (or rebuild if the key changed) the Gemini client."""
    global _gemini_client, _gemini_key
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise LLMError(None, "GEMINI_API_KEY is not set. On Streamlit Cloud add it under "
                             "Manage app → Settings → Secrets.")
    if _gemini_client is None or key != _gemini_key:
        from google import genai
        _gemini_client = genai.Client(api_key=key)
        _gemini_key = key
    return _gemini_client


def _gemini_generate_json(parts: List[Part], schema: Type[T], system: str | None) -> T:
    from google.genai import types
    from google.genai import errors as genai_errors

    contents = []
    for p in parts:
        if isinstance(p, ImagePart):
            contents.append(types.Part.from_bytes(data=p.data, mime_type=p.mime_type))
        else:
            contents.append(p)

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        system_instruction=system,
        temperature=0,  # grading must be deterministic / reproducible
    )
    try:
        resp = _get_gemini_client().models.generate_content(
            model=_model(), contents=contents, config=config,
        )
    except genai_errors.APIError as e:
        # surface the REAL status + message (Streamlit otherwise redacts it)
        status = getattr(e, "code", None) or getattr(e, "status_code", None)
        message = getattr(e, "message", None) or str(e)
        raise LLMError(status, message) from e

    # resp.parsed is already a `schema` instance; fall back to parsing raw text.
    if getattr(resp, "parsed", None) is not None:
        return resp.parsed  # type: ignore[return-value]
    return schema.model_validate_json(resp.text)


# --------------------------------------------------------------------------- #
# Claude / OpenAI — same contract, implemented when a key is swapped in        #
# --------------------------------------------------------------------------- #
def _claude_generate_json(parts: List[Part], schema: Type[T], system: str | None) -> T:
    raise NotImplementedError("Claude provider path: implement with anthropic SDK when needed.")


def _openai_generate_json(parts: List[Part], schema: Type[T], system: str | None) -> T:
    raise NotImplementedError("OpenAI provider path: implement with openai SDK when needed.")
