"""Small in-process rate limiter used when no shared limiter is configured.

It is intentionally conservative and protects browser-facing sensitive routes
in a single-process prototype. Deployments with multiple workers should
replace it with a shared Flask-Limiter/Redis backend.
"""

import time
from collections import defaultdict, deque
from threading import Lock

from flask import abort, request


class SensitiveRouteLimiter:
    def __init__(self):
        self._events = defaultdict(deque)
        self._lock = Lock()

    def enforce(self, limit, window_seconds):
        client = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
        key = (client, request.endpoint or request.path)
        now = time.monotonic()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] >= window_seconds:
                events.popleft()
            if len(events) >= limit:
                abort(429)
            events.append(now)


limiter = SensitiveRouteLimiter()
