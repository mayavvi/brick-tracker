"""Password hashing for local allowlist auth (SHA-256 + random salt)."""

from __future__ import annotations

import hashlib
import secrets


def hash_password(plain: str) -> str:
    """Return stored credential string: $sha256$<salt_hex>$<digest_hex>."""
    salt = secrets.token_bytes(16)
    salt_hex = salt.hex()
    digest = hashlib.sha256(salt + plain.encode("utf-8")).hexdigest()
    return f"$sha256${salt_hex}${digest}"


def verify_password(plain: str, stored: str) -> bool:
    """Constant-time compare of plain password against stored hash string."""
    if not stored or not stored.startswith("$sha256$"):
        return False
    parts = stored.split("$")
    if len(parts) != 4 or parts[1] != "sha256":
        return False
    salt_hex, want = parts[2], parts[3]
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    if len(want) != 64:  # sha256 hex
        return False
    got = hashlib.sha256(salt + plain.encode("utf-8")).hexdigest()
    return secrets.compare_digest(got, want)
