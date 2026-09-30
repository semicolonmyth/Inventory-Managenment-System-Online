"""Security tests for the password hashing helper.

These lock in PBKDF2 behavior *and* the backward-compatible ``authenticate``
flow now used by the login screen: hashed rows verify via constant-time
comparison, legacy plaintext rows still log in and are flagged for upgrade.
"""

import pytest

from utils.security import (
    authenticate,
    hash_password,
    is_legacy_plaintext,
    verify_password,
)


@pytest.mark.security
class TestPasswordHashing:
    def test_hash_is_not_plaintext(self):
        h = hash_password("s3cret")
        assert h != "s3cret"
        assert "s3cret" not in h

    def test_hash_is_verifiable(self):
        h = hash_password("s3cret")
        assert verify_password("s3cret", h) is True

    def test_wrong_password_rejected(self):
        h = hash_password("s3cret")
        assert verify_password("wrong", h) is False

    def test_salts_are_unique(self):
        # Same password -> different hash (per-hash random salt).
        assert hash_password("same") != hash_password("same")

    def test_legacy_plaintext_never_authenticates(self):
        # A stored raw password like "admin" must NOT pass verification,
        # demonstrating why the plaintext flow is unsafe.
        assert verify_password("admin", "admin") is False

    def test_malformed_hash_is_rejected_gracefully(self):
        assert verify_password("x", "not-a-valid-hash") is False
        assert verify_password("x", None) is False

    def test_none_password_raises_on_hash(self):
        with pytest.raises(ValueError):
            hash_password(None)


@pytest.mark.security
class TestAuthenticate:
    """Backward-compatible login path used by ui/login.py."""

    def test_hashed_row_ok_no_upgrade(self):
        h = hash_password("hunter2")
        ok, needs_upgrade = authenticate(h, "hunter2")
        assert ok is True
        assert needs_upgrade is False

    def test_hashed_row_wrong_password(self):
        h = hash_password("hunter2")
        ok, needs_upgrade = authenticate(h, "nope")
        assert ok is False
        assert needs_upgrade is False

    def test_legacy_plaintext_matches_and_flags_upgrade(self):
        # An existing install may still hold a raw "admin"; it must still log
        # in once and be marked for transparent re-hash.
        ok, needs_upgrade = authenticate("admin", "admin")
        assert ok is True
        assert needs_upgrade is True

    def test_legacy_plaintext_wrong_password(self):
        ok, needs_upgrade = authenticate("admin", "guess")
        assert ok is False
        assert needs_upgrade is False

    def test_is_legacy_detection(self):
        assert is_legacy_plaintext("admin") is True
        assert is_legacy_plaintext(hash_password("admin")) is False
        assert is_legacy_plaintext(None) is False
