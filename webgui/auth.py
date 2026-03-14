"""
Entra ID SAML Authentication for Ansible Playbook Builder.

Handles SAML login/logout, session management, and user extraction.
Uses python3-saml (OneLogin's SAML toolkit).

Setup:
  1. Register an Enterprise Application in Entra ID
  2. Set SSO to SAML
  3. Set Reply URL to: https://your-host/api/auth/saml/acs
  4. Set Entity ID to: https://your-host/api/auth/saml/metadata
  5. Download Federation Metadata XML or note the IdP metadata URL
  6. Copy saml/settings.json.example -> saml/settings.json and fill in values
"""

import os
import json
import time
import uuid
import hashlib
import hmac
from functools import wraps
from typing import Optional

from fastapi import Request, Response, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware

# python3-saml
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.utils import OneLogin_Saml2_Utils

# ─── Config ───────────────────────────────────────────────────
SAML_DIR = os.environ.get("SAML_DIR", os.path.join(os.path.dirname(__file__), "saml"))
SESSION_SECRET = os.environ.get("SESSION_SECRET", uuid.uuid4().hex)
SESSION_COOKIE = "pb_session"
SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", "28800"))  # 8 hours

# In-memory session store. For multi-instance, swap for Redis.
_sessions: dict = {}

# Paths that don't require auth
PUBLIC_PATHS = {
    "/api/auth/saml/login",
    "/api/auth/saml/acs",
    "/api/auth/saml/metadata",
    "/api/auth/saml/sls",
    "/api/health",
}


def _sign_session_id(session_id: str) -> str:
    """HMAC sign a session ID."""
    sig = hmac.new(SESSION_SECRET.encode(), session_id.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{session_id}.{sig}"


def _verify_session_id(signed: str) -> Optional[str]:
    """Verify and extract session ID."""
    if "." not in signed:
        return None
    session_id, sig = signed.rsplit(".", 1)
    expected = hmac.new(SESSION_SECRET.encode(), session_id.encode(), hashlib.sha256).hexdigest()[:16]
    if hmac.compare_digest(sig, expected):
        return session_id
    return None


def get_session(request: Request) -> Optional[dict]:
    """Get the current user session from cookie."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    session_id = _verify_session_id(cookie)
    if not session_id:
        return None
    session = _sessions.get(session_id)
    if not session:
        return None
    if time.time() > session.get("expires", 0):
        _sessions.pop(session_id, None)
        return None
    return session


def create_session(user_data: dict) -> str:
    """Create a new session, return signed cookie value."""
    session_id = uuid.uuid4().hex
    _sessions[session_id] = {
        **user_data,
        "created": time.time(),
        "expires": time.time() + SESSION_MAX_AGE,
    }
    return _sign_session_id(session_id)


def destroy_session(request: Request):
    """Remove session."""
    cookie = request.cookies.get(SESSION_COOKIE)
    if cookie:
        session_id = _verify_session_id(cookie)
        if session_id:
            _sessions.pop(session_id, None)


def _prepare_saml_request(request: Request) -> dict:
    """Convert FastAPI request to format python3-saml expects."""
    url = str(request.url)
    return {
        "https": "on" if request.url.scheme == "https" else "off",
        "http_host": request.headers.get("x-forwarded-host", request.url.hostname),
        "server_port": request.headers.get("x-forwarded-port", str(request.url.port or 443)),
        "script_name": request.url.path,
        "get_data": dict(request.query_params),
        "post_data": {},  # filled in ACS handler
    }


def init_saml_auth(req_data: dict) -> OneLogin_Saml2_Auth:
    """Initialize SAML auth object."""
    return OneLogin_Saml2_Auth(req_data, custom_base_path=SAML_DIR)


# ─── Middleware ───────────────────────────────────────────────

class SAMLAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces SAML authentication.
    Unauthenticated requests get redirected to the SAML login flow.
    API calls get a 401 instead of redirect.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always allow public paths
        if path in PUBLIC_PATHS:
            return await call_next(request)

        # Allow static assets
        if path.endswith((".js", ".css", ".ico", ".png", ".svg", ".woff", ".woff2")):
            return await call_next(request)

        # Check session
        session = get_session(request)
        if session:
            # Attach user info to request state
            request.state.user = session
            return await call_next(request)

        # Not authenticated
        if path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="Not authenticated")

        # Redirect browser requests to SAML login
        return RedirectResponse(url="/api/auth/saml/login")


# ─── Route Handlers (register on your FastAPI app) ───────────

def register_saml_routes(app):
    """Register SAML auth endpoints on the FastAPI app."""

    @app.get("/api/auth/saml/login")
    async def saml_login(request: Request):
        """Initiate SAML login — redirects to Entra ID."""
        req_data = _prepare_saml_request(request)
        auth = init_saml_auth(req_data)
        login_url = auth.login()
        return RedirectResponse(url=login_url)

    @app.post("/api/auth/saml/acs")
    async def saml_acs(request: Request):
        """Assertion Consumer Service — Entra posts SAML response here."""
        form = await request.form()
        req_data = _prepare_saml_request(request)
        req_data["post_data"] = dict(form)

        auth = init_saml_auth(req_data)
        auth.process_response()
        errors = auth.get_errors()

        if errors:
            error_reason = auth.get_last_error_reason()
            return HTMLResponse(
                f"<h2>SAML Authentication Failed</h2><p>{', '.join(errors)}</p><p>{error_reason}</p>"
                f"<p><a href='/api/auth/saml/login'>Try again</a></p>",
                status_code=400,
            )

        if not auth.is_authenticated():
            return HTMLResponse(
                "<h2>Authentication failed</h2><p><a href='/api/auth/saml/login'>Try again</a></p>",
                status_code=401,
            )

        # Extract user attributes from SAML assertion
        attrs = auth.get_attributes()
        name_id = auth.get_nameid()

        user_data = {
            "email": name_id,
            "name": _first(attrs.get("http://schemas.microsoft.com/identity/claims/displayname"))
                    or _first(attrs.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"))
                    or name_id,
            "upn": _first(attrs.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn")) or name_id,
            "groups": attrs.get("http://schemas.microsoft.com/ws/2008/06/identity/claims/groups", []),
            "roles": attrs.get("http://schemas.microsoft.com/ws/2008/06/identity/claims/role", []),
        }

        cookie_value = create_session(user_data)

        # Redirect to app with session cookie
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            SESSION_COOKIE, cookie_value,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            secure=True,
            samesite="lax",
        )
        return response

    @app.get("/api/auth/saml/metadata")
    async def saml_metadata(request: Request):
        """SP metadata — give this URL to Entra when configuring the app."""
        req_data = _prepare_saml_request(request)
        auth = init_saml_auth(req_data)
        metadata = auth.get_settings().get_sp_metadata()
        errors = auth.get_settings().validate_metadata(metadata)
        if errors:
            raise HTTPException(400, detail=", ".join(errors))
        return Response(content=metadata, media_type="application/xml")

    @app.get("/api/auth/saml/sls")
    async def saml_sls(request: Request):
        """Single Logout Service."""
        req_data = _prepare_saml_request(request)
        auth = init_saml_auth(req_data)
        auth.process_slo()
        destroy_session(request)
        response = RedirectResponse(url="/")
        response.delete_cookie(SESSION_COOKIE)
        return response

    @app.get("/api/auth/logout")
    async def logout(request: Request):
        """Local logout (or initiate SAML SLO)."""
        destroy_session(request)
        response = RedirectResponse(url="/")
        response.delete_cookie(SESSION_COOKIE)
        return response

    @app.get("/api/auth/me")
    async def auth_me(request: Request):
        """Return current user info."""
        session = get_session(request)
        if not session:
            raise HTTPException(401, "Not authenticated")
        return {
            "email": session.get("email"),
            "name": session.get("name"),
            "upn": session.get("upn"),
            "groups": session.get("groups", []),
        }


def _first(lst):
    """Get first element of list or None."""
    if lst and isinstance(lst, list):
        return lst[0]
    return lst
