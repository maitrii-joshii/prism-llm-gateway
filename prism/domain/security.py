"""Security utilities for Prism."""

import hashlib


def hash_api_key(raw_key: str) -> str:
    """Convert a raw API key into its SHA-256 hexadecimal hash."""

    return hashlib.sha256(
        raw_key.encode("utf-8")
    ).hexdigest()
