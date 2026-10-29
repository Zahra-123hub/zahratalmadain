"""Small security helpers: password policy and sign-in throttling."""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import LoginAttempt

# Passwords people choose all the time; matched ignoring case, spaces and trailing digits/symbols.
COMMON_PASSWORDS = {
    "password", "passw0rd", "password1", "password123", "qwerty", "qwertyuiop", "qwertyuiop123",
    "azerty", "azertyuiop", "asdfghjkl", "asdfghjkl123", "zxcvbnm", "iloveyou", "welcome", "welcome123",
    "letmein", "admin", "administrator", "adminadmin", "admin123", "changeme", "trustno1", "abc123",
    "monkey", "dragon", "football", "baseball", "sunshine", "princess", "superman", "master", "login",
    "zahra", "zahrat", "zahratalmadain", "almadain", "kindergarten", "kita", "roda", "damascus", "syria",
    "123456789", "1234567890", "12345678901", "123456789012", "111111111111", "000000000000",
    "123123123123", "abcdefghijkl", "abcdefghijklmnop", "passwordpassword",
}

PASSWORD_MIN_LENGTH = 12


def password_problem(password: str, username: str = "") -> str | None:
    """Returns an English reason code-phrase when the password is too weak, else None.

    Length matters more than complexity: 12+ characters, not a well known password, not built
    from the username, not only digits and not just a few repeated characters."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return "Password is too short."
    lowered = password.lower().replace(" ", "")
    stripped = lowered.rstrip("0123456789!@#$%^&*._-")
    if lowered in COMMON_PASSWORDS or stripped in COMMON_PASSWORDS:
        return "Password is too common or too easy to guess."
    name = username.strip().lower()
    if len(name) >= 3 and name in lowered:
        return "Password must not contain the username."
    if password.isdigit():
        return "Password must not be only digits."
    if len(set(password)) < 6:
        return "Password needs at least 6 different characters."
    return None


# --- throttling ---------------------------------------------------------------------------


def throttle_key(secret: str, kind: str, value: str) -> str:
    """Opaque key for the attempts table: no raw usernames or addresses are stored."""
    return hmac.new(secret.encode(), f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def failures_since(session: Session, key: str, seconds: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return (
        session.scalar(
            select(func.count())
            .select_from(LoginAttempt)
            .where(LoginAttempt.username_hash == key, LoginAttempt.attempted_at >= cutoff)
        )
        or 0
    )


def record_attempt(session: Session, key: str) -> None:
    session.add(LoginAttempt(username_hash=key, attempted_at=datetime.now(timezone.utc)))


class MemoryThrottle:
    """Sliding-window limiter in process memory; for the one endpoint that works without a database."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def blocked(self, key: str, limit: int, window: int) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < window]
            self._hits[key] = hits
            return len(hits) >= limit

    def record(self, key: str) -> None:
        with self._lock:
            self._hits.setdefault(key, []).append(time.monotonic())

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()
