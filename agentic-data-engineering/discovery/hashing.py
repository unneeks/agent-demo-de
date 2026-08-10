"""File-content hashing for discovery.

Deliberately separate from ``persistence.memory.repositories.content_hash``:
that function hashes a dict payload (``json.dumps(sort_keys=True)`` then
sha256). This module hashes raw file bytes -- a different input shape,
used for the golden-fixture staleness check and ``DeliveryArtifact.content_hash``.
"""

from __future__ import annotations

import hashlib


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))
