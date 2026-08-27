"""Local action authentication.

Action and system-inspection endpoints require the high-entropy action token
(sent as a bearer credential) and a per-client session id. The token identifies
the single local operator; the session id isolates concurrent browser tabs so
one client can never touch another's proposals. The token is compared in
constant time and never logged.
"""

from __future__ import annotations

import re

from fastapi import HTTPException, Request

from .actions import Principal
from .config import Settings

LOCAL_USER = "local-operator"
_SESSION_RE = re.compile(r"^[A-Za-z0-9_\-]{16,128}$")
_USER_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def authenticate(request: Request, settings: Settings) -> Principal:
    if not settings.actions_available:
        raise HTTPException(status_code=503, detail="action token is not configured on the server")

    header = request.headers.get("authorization", "")
    scheme, _, credential = header.partition(" ")
    if scheme.lower() != "bearer" or not credential:
        raise HTTPException(status_code=401, detail="a bearer action token is required")
    if not settings.token_matches(credential):
        raise HTTPException(status_code=401, detail="invalid action token")

    session_id = request.headers.get("x-alfred-session", "")
    if not _SESSION_RE.match(session_id):
        raise HTTPException(
            status_code=400,
            detail="a valid X-Alfred-Session id (16-128 url-safe chars) is required",
        )

    user_id = request.headers.get("x-alfred-user", LOCAL_USER) or LOCAL_USER
    if not _USER_RE.match(user_id):
        raise HTTPException(status_code=400, detail="invalid X-Alfred-User id")

    return Principal(user_id=user_id, session_id=session_id)
