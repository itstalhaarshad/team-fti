"""Storage factory — selects the backend from env (same pattern as core/llm.py).

STORAGE_BACKEND=local      -> file-backed Memory under data/batches/ (default).
STORAGE_BACKEND=firestore  -> Firebase Firestore, scoped per signed-in teacher (uid).

Both backends expose the SAME method surface (see core/memory.Memory), so the agents, app,
and CLI never know which is behind them. uid is required for firestore, ignored by local.
"""
from __future__ import annotations

import os
from typing import List, Optional

from core.memory import Memory
from core.memory import list_batches as _local_list_batches


def _backend() -> str:
    return os.environ.get("STORAGE_BACKEND", "local").strip().lower()


def get_store(batch_id: str, uid: Optional[str] = None):
    """Return a store for one batch. Firestore needs a signed-in uid; without one (auth disabled)
    we fall back to local file storage so the app works with the login screen turned off."""
    if _backend() == "firestore" and uid:
        from core.firestore_store import FirestoreStore
        return FirestoreStore(batch_id, uid)
    return Memory(batch_id)


def list_batches(uid: Optional[str] = None) -> List[dict]:
    """List batch summaries for the home dashboard, scoped to the user when on firestore."""
    if _backend() == "firestore" and uid:
        from core.firestore_store import list_batches_fs
        return list_batches_fs(uid)
    return _local_list_batches()
