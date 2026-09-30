"""Password hashing helpers (stdlib only, no new dependencies).

The application currently stores user passwords in PLAIN TEXT
(``User.password_hash`` holds the raw password and login compares it
directly). That is a critical security defect. This module provides a
proper PBKDF2-HMAC-SHA256 hash/verify pair so the login flow and the
seed routine can be migrated to salted hashes.

Adopting these in ``ui/login.py`` and ``db/local_db.init_db`` changes
authentication behavior (and requires hashing existing rows), so it is
proposed rather than silently applied -- see the audit report.
"""

import hashlib
import hmac
import secrets

_ALGO = "sha256"
_ITERATIONS = 210_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Return a salted PBKDF2 hash string safe to store in ``password_hash``.

    Format: ``pbkdf2_<algo>_<iterations$salt_hex$hash_hex``
    """
    if password is None:
        raise ValueError("password must not be None")
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(_ALGO, password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_{_ALGO}_{_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of ``password`` against a stored hash.

    Returns False for any malformed/legacy value instead of raising.
    """
    if not isinstance(stored, str) or not stored.startswith("pbkdf2_"):
        # Legacy plaintext row or garbage: never authenticates via this path.
        return False
    try:
        prefix, salt_hex, hash_hex = stored.split("$")
        _, algo, iterations = prefix.split("_")
        expected = bytes.fromhex(hash_hex)
        salt = bytes.fromhex(salt_hex)
        candidate = hashlib.pbkdf2_hmac(
            algo, (password or "").encode("utf-8"), salt, int(iterations)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


def is_legacy_plaintext(stored: object) -> bool:
    """True if the stored value is not a PBKDF2 hash (i.e. legacy plaintext)."""
    return isinstance(stored, str) and not stored.startswith("pbkdf2_")


def authenticate(stored: object, supplied: str) -> tuple[bool, bool]:
    """Backward-compatible login check.

    Returns ``(ok, needs_upgrade)``:
    * ``ok``            -- did the supplied password match?
    * ``needs_upgrade`` -- the row is legacy plaintext and matched, so the
      caller should re-store it as a hash (transparent migration).

    Modern PBKDF2 rows use constant-time verification and never need upgrade.
    """
    if is_legacy_plaintext(stored):
        # Legacy rows stored the raw password; compare in constant time.
        ok = hmac.compare_digest(str(stored), str(supplied or ""))
        return ok, ok
    return verify_password(supplied, stored), False
