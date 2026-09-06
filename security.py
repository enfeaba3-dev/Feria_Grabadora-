from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

from flask import g, jsonify, request

LOGGER = logging.getLogger(__name__)

CSRF_HEADER = "X-CSRF-Token"
CSRF_FIELD = "csrf_token"
CSRF_COOKIE = "feria_csrf"
SESSION_COOKIE = "feria_sid"
INTERNAL_HEADER = "X-Internal-Token"

_INTERNAL_TOKEN: str | None = None
_INTERNAL_TOKEN_PATH: Path | None = None

# Sliding-window rate limit: (max_requests, window_seconds).
RATE_LIMITS: dict[tuple[str, str], tuple[int, float]] = {
    ("/api/transcribe", "POST"): (20, 60.0),
    ("/api/transcribe", "PUT"): (20, 60.0),
    ("/api/config", "PUT"): (10, 60.0),
    ("/api/agent", "POST"): (30, 60.0),
    ("/api/model/warmup", "POST"): (5, 60.0),
    ("/api/history", "POST"): (20, 60.0),
    ("/api/history", "DELETE"): (30, 60.0),
    ("/api/client-log", "POST"): (60, 60.0),
    ("/api/notify", "POST"): (10, 60.0),
    ("/api/support-bundle", "GET"): (3, 60.0),
}


class _TokenStore:
    """In-memory CSRF token store keyed by session id.

    For a localhost-only app, the session id is just a random cookie value
    that the browser keeps. We rotate the session id on first contact and
    bind each issued token to that id, so a cross-tab attacker cannot
    reuse a leaked token from a different origin.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, dict[str, float]] = {}
        # Tokens older than 8h are evicted lazily.
        self._ttl_seconds = 8 * 3600

    def issue(self, sid: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            bucket = self._sessions.setdefault(sid, {})
            bucket[token] = time.time()
            self._evict_locked(sid)
        return token

    def validate(self, sid: str, token: str | None) -> bool:
        if not token:
            return False
        if not sid:
            return False
        with self._lock:
            bucket = self._sessions.get(sid)
            if not bucket:
                return False
            self._evict_locked(sid)
            return token in bucket

    def rotate_session(self, old_sid: str | None) -> str:
        new_sid = secrets.token_urlsafe(24)
        with self._lock:
            if old_sid and old_sid in self._sessions:
                self._sessions[new_sid] = self._sessions.pop(old_sid)
        return new_sid

    def _evict_locked(self, sid: str) -> None:
        bucket = self._sessions.get(sid)
        if not bucket:
            return
        cutoff = time.time() - self._ttl_seconds
        for token, ts in list(bucket.items()):
            if ts < cutoff:
                bucket.pop(token, None)
        if not bucket:
            self._sessions.pop(sid, None)


_TOKENS = _TokenStore()


def ensure_session(response):
    """Issue or rotate the session cookie if missing. Must run on every
    response so a fresh token is always available to the page."""
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        sid = _TOKENS.rotate_session(None)
    g.session_id = sid
    # Set cookies only if changed; Flask sets them if value differs.
    response.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        samesite="Strict",
        secure=False,  # localhost only; no TLS
        max_age=8 * 3600,
        path="/",
    )
    csrf = _TOKENS.issue(sid)
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        httponly=False,  # JS must read it to send header
        samesite="Strict",
        secure=False,
        max_age=8 * 3600,
        path="/",
    )
    g.csrf_token = csrf
    return response


def _is_unsafe_method(method: str) -> bool:
    return method.upper() in {"POST", "PUT", "PATCH", "DELETE"}


def csrf_protect(view: Callable):
    """Decorator: require a valid CSRF token on unsafe methods.

    For unsafe methods we accept the token from header, form field, or
    JSON body, and verify it matches the session id.
    """

    from functools import wraps

    @wraps(view)
    def wrapper(*args, **kwargs):
        if _is_unsafe_method(request.method):
            # Internal child processes (the dictation agent) use a shared
            # secret instead of a browser CSRF token. This is safe because
            # the secret only lives in the runtime folder and the agent is
            # launched as a child of the server.
            internal = request.headers.get(INTERNAL_HEADER, "")
            if _INTERNAL_TOKEN and constant_time_eq(internal, _INTERNAL_TOKEN):
                return view(*args, **kwargs)

            sid = request.cookies.get(SESSION_COOKIE, "")
            token = request.headers.get(CSRF_HEADER)
            if not token:
                token = request.form.get(CSRF_FIELD)
            if not token:
                # JSON body fallback
                try:
                    payload = request.get_json(silent=True) or {}
                    token = payload.get(CSRF_FIELD)
                except Exception:
                    token = None
            if not _TOKENS.validate(sid, token):
                LOGGER.warning(
                    "CSRF rechazado | sid=%s | ip=%s | path=%s",
                    bool(sid),
                    request.remote_addr,
                    request.path,
                )
                return (
                    jsonify(
                        {
                            "error": {
                                "code": "CSRF_FAILED",
                                "message": "Token CSRF invalido o caducado.",
                            },
                            "request_id": getattr(g, "request_id", None),
                        }
                    ),
                    403,
                )
        return view(*args, **kwargs)

    return wrapper


def init_internal_token(path: Path) -> str:
    """Generate (or load) a shared secret used by child processes to
    authenticate to the API. Stored in the runtime folder, which is
    created with 0o700 perms on POSIX and inherits user-only ACLs on
    Windows."""
    global _INTERNAL_TOKEN, _INTERNAL_TOKEN_PATH
    _INTERNAL_TOKEN_PATH = path
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = None
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8").strip()
        except OSError:
            existing = None
    if existing and len(existing) >= 32:
        _INTERNAL_TOKEN = existing
    else:
        _INTERNAL_TOKEN = secrets.token_urlsafe(32)
        try:
            path.write_text(_INTERNAL_TOKEN, encoding="utf-8")
        except OSError as exc:
            LOGGER.warning("No se pudo guardar internal token: %s", exc)
    return _INTERNAL_TOKEN


def get_internal_token() -> str | None:
    return _INTERNAL_TOKEN


# --- Rate limiting ---------------------------------------------------------
class _RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # remote_addr -> deque[timestamps]
        self._buckets: dict[str, deque[float]] = {}

    def check(self, key: str, max_requests: int, window: float) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = time.time()
        with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            cutoff = now - window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= max_requests:
                retry = max(1, int(window - (now - bucket[0])) + 1)
                return False, retry
            bucket.append(now)
            return True, 0

    def cleanup(self) -> None:
        with self._lock:
            now = time.time()
            for key in list(self._buckets.keys()):
                bucket = self._buckets[key]
                while bucket and bucket[0] < now - 3600:
                    bucket.popleft()
                if not bucket:
                    self._buckets.pop(key, None)


_LIMITER = _RateLimiter()


def rate_limit(view: Callable):
    """Decorator: per-IP sliding window rate limit based on RATE_LIMITS."""
    from functools import wraps

    @wraps(view)
    def wrapper(*args, **kwargs):
        limit = RATE_LIMITS.get((request.path, request.method.upper()))
        if limit:
            max_requests, window = limit
            key = f"{request.remote_addr}|{request.path}"
            allowed, retry = _LIMITER.check(key, max_requests, window)
            if not allowed:
                LOGGER.warning(
                    "Rate limit | ip=%s | path=%s | retry=%s",
                    request.remote_addr,
                    request.path,
                    retry,
                )
                resp = jsonify(
                    {
                        "error": {
                            "code": "RATE_LIMITED",
                            "message": f"Demasiadas peticiones. Espera {retry}s.",
                        },
                        "request_id": getattr(g, "request_id", None),
                    }
                )
                resp.status_code = 429
                resp.headers["Retry-After"] = str(retry)
                return resp
        return view(*args, **kwargs)

    return wrapper


# --- Security headers ------------------------------------------------------
def apply_security_headers(response):
    """Add hardening headers to every response. Safe for localhost; the
    CSP is permissive enough for the bundled web UI but blocks third-party
    loads and inline event handlers."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "microphone=(self), camera=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    # The UI loads its own CSS/JS from same origin and uses sendBeacon to
    # /api/client-log; no third-party domains are needed.
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "media-src 'self' blob: mediastream:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "connect-src 'self'; "
        "worker-src 'self' blob:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'",
    )
    # No HSTS here: app binds to 127.0.0.1, not HTTPS.
    return response


def hash_file(path, *, algo="sha256", chunk=1024 * 1024):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def constant_time_eq(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def safe_int(value, default: int, *, min_value: int, max_value: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(result, max_value))
