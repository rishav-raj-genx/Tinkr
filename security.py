import math
import threading
import time
from datetime import timedelta
from functools import wraps
from uuid import uuid4

from flask import Flask, jsonify, request, session

from config import config


class RateLimiter:
    """Thread-safe in-memory sliding-window rate limiter with automatic stale key cleanup."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, str], list[float]] = {}
        self._op_count = 0

    def is_allowed(
        self,
        key: tuple[str, str, str],
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """Checks if request under key is allowed.

        Returns:
            tuple[bool, int]: (allowed, retry_after_seconds)
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            self._op_count += 1
            if self._op_count >= 100:
                self._cleanup_stale(now)
                self._op_count = 0

            timestamps = self._requests.get(key, [])
            filtered = [t for t in timestamps if t > cutoff]

            if len(filtered) >= max_requests:
                oldest = filtered[0]
                retry_after = max(1, math.ceil(oldest + window_seconds - now))
                self._requests[key] = filtered
                return False, retry_after

            filtered.append(now)
            self._requests[key] = filtered
            return True, 0

    def _cleanup_stale(self, now: float) -> None:
        """Purges keys whose timestamps are entirely older than maximum potential window (900s)."""
        max_history_cutoff = now - 900
        keys_to_remove = []
        for k, timestamps in self._requests.items():
            valid_stamps = [t for t in timestamps if t > max_history_cutoff]
            if not valid_stamps:
                keys_to_remove.append(k)
            else:
                self._requests[k] = valid_stamps

        for k in keys_to_remove:
            self._requests.pop(k, None)

    def reset(self) -> None:
        """Resets all recorded rate limit buckets (useful for tests)."""
        with self._lock:
            self._requests.clear()
            self._op_count = 0


rate_limiter = RateLimiter()


def get_client_ip() -> str:
    """Extracts client IP, resolving X-Forwarded-For when behind reverse proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def rate_limit(bucket: str, max_requests: int, window_seconds: int):
    """Decorator applying sliding-window rate limits keyed by (bucket, client_ip, sid)."""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = get_client_ip()
            sid, _ = get_or_create_session_identity()
            key = (bucket, client_ip, sid)

            allowed, retry_after = rate_limiter.is_allowed(key, max_requests, window_seconds)
            if not allowed:
                response = jsonify({
                    "error": "Rate limit exceeded. Please try again shortly."
                })
                response.status_code = 429
                response.headers["Retry-After"] = str(retry_after)
                return response

            return f(*args, **kwargs)

        return decorated_function

    return decorator


def configure_security(app: Flask) -> None:
    """Configures Flask cryptographically signed session cookies and security headers."""
    app.secret_key = config.SECRET_KEY
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = not config.DEBUG
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

    @app.before_request
    def enforce_dynamic_cookie_security():
        # Adaptively enforce secure cookies when reverse proxy terminates HTTPS
        if request.headers.get("X-Forwarded-Proto", "").lower() == "https":
            app.config["SESSION_COOKIE_SECURE"] = True


def get_or_create_session_identity() -> tuple[str, str]:
    """Retrieves or creates the cryptographically signed session identity.

    Returns:
        tuple[str, str]: (sid, role) where sid is the server-managed storage partition key
        and role is either 'guest' or 'owner'.
    """
    session.permanent = True
    if "sid" not in session:
        session["sid"] = f"visitor_{uuid4().hex[:16]}"
    if "role" not in session:
        session["role"] = "guest"
    return session["sid"], session["role"]


def rotate_session_identity() -> tuple[str, str]:
    """Rotates session identity on logout or privilege reset."""
    session.clear()
    session.permanent = True
    session["sid"] = f"visitor_{uuid4().hex[:16]}"
    session["role"] = "guest"
    return session["sid"], session["role"]


def is_owner_live_mode() -> bool:
    """Returns True if the current session is an owner with valid Google credentials."""
    return session.get("role") == "owner" and config.TOKEN_PATH.exists()


def get_workspace_mode() -> str:
    """Returns 'live' if authenticated as owner with valid token, else 'sandbox'."""
    return "live" if is_owner_live_mode() else "sandbox"
