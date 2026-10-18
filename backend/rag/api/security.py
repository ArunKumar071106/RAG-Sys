"""Request limits: per-client rate limiting, body size cap, admin authentication."""

from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimiter:
    """Sliding-window limiter keyed by client IP (in-memory; use a shared store behind multiple workers)."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        if self.per_minute <= 0:
            return True, 0
        now = time.monotonic()
        with self.lock:
            window = self.hits[key]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= self.per_minute:
                return False, int(60 - (now - window[0])) + 1
            window.append(now)
            if len(self.hits) > 10_000:  # bound memory
                for k in [k for k, v in self.hits.items() if not v][:5000]:
                    del self.hits[k]
            return True, 0


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > self.max_bytes:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        return await call_next(request)


def make_rate_limit_dependency(limiter: RateLimiter):
    async def dependency(request: Request) -> None:
        allowed, retry_after = limiter.check(client_key(request))
        if not allowed:
            raise HTTPException(status_code=429, detail="Too many requests, please slow down.",
                                headers={"Retry-After": str(retry_after)})
    return dependency


def make_admin_dependency(token: str):
    async def dependency(authorization: str = Header(default="")) -> None:
        if not token:
            raise HTTPException(status_code=503, detail="Admin endpoints are disabled (ADMIN_TOKEN not set)")
        scheme, _, supplied = authorization.partition(" ")
        if scheme.lower() != "bearer" or not hmac.compare_digest(supplied.encode(), token.encode()):
            raise HTTPException(status_code=401, detail="Invalid admin token", headers={"WWW-Authenticate": "Bearer"})
    return dependency
