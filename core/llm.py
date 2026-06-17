"""Thin, provider-agnostic LLM/vision wrapper — the ONLY place a vendor SDK is imported.

Public surface the agents use:
    generate_json(parts, schema, system=None) -> dict

`parts` is a list of either str (text) or ImagePart (bytes + mime). The wrapper routes to the
provider named by LLM_PROVIDER (default 'gemini'), using model LLM_MODEL, and forces structured
JSON conforming to `schema` (a Pydantic BaseModel subclass).

Phase 1 implements the Gemini path. Claude/OpenAI paths land behind the same signature later.
"""
# TODO(phase1): implement build_client(), generate_json() for gemini via google-genai.
raise NotImplementedError("core/llm.py — implemented in Phase 1")
