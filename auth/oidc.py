"""Duke OIDC client configuration (Authlib)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from authlib.integrations.flask_client import OAuth
from flask import has_request_context, request

from dbutils.env import load_repo_env

DUKE_OIDC_DISCOVERY = "https://oauth.oit.duke.edu/oidc/.well-known/openid-configuration"
DUKE_OIDC_SCOPES = "openid profile email"
LOCAL_REDIRECT_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}
LOCAL_REDIRECT_HOST = "localhost"

oauth = OAuth()


def init_oauth(app) -> None:
    load_repo_env()
    client_id = os.environ.get("DUKE_OIDC_CLIENT_ID", "").strip()
    client_secret = os.environ.get("DUKE_OIDC_CLIENT_SECRET", "").strip()
    if not client_id:
        return
    oauth.init_app(app)
    oauth.register(
        name="duke",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url=DUKE_OIDC_DISCOVERY,
        client_kwargs={"scope": DUKE_OIDC_SCOPES},
    )


def redirect_uri() -> str:
    load_repo_env()
    uri = os.environ.get("DUKE_OIDC_REDIRECT_URI", "").strip()
    request_uri = _request_redirect_uri()
    caddy_uri = _caddy_redirect_uri()
    if caddy_uri and (not uri or _is_local_redirect_uri(uri)):
        return caddy_uri
    if request_uri and (not uri or _is_local_redirect_uri(uri)):
        return request_uri
    if uri:
        return uri
    return _local_redirect_uri(LOCAL_REDIRECT_HOST)


def _caddy_redirect_uri() -> str | None:
    domain = os.environ.get("CADDY_DOMAIN", "").strip().strip("/")
    if not domain:
        return None
    base = domain if "://" in domain else f"https://{domain}"
    return f"{base}/login"


def _request_redirect_uri() -> str | None:
    if not has_request_context():
        return None
    host = _first_forwarded_value("X-Forwarded-Host") or request.host
    host = _netloc(host)
    hostname = _hostname(host)
    if not hostname:
        return None
    if hostname in LOCAL_REDIRECT_HOSTS:
        return _local_redirect_uri(hostname, requested_port=_port(host))
    scheme = _first_forwarded_value("X-Forwarded-Proto") or request.scheme or "http"
    if scheme == "http":
        scheme = "https"
    return f"{scheme}://{host}/login"


def _first_forwarded_value(header: str) -> str:
    return request.headers.get(header, "").split(",", 1)[0].strip()


def _local_redirect_uri(hostname: str, *, requested_port: str | None = None) -> str:
    return f"http://{hostname}:{_local_port(requested_port=requested_port)}/login"


def _local_port(*, requested_port: str | None = None) -> str:
    forward_port = os.environ.get("APP_FORWARD_PORT", "").strip()
    if requested_port and forward_port and requested_port == forward_port:
        return requested_port
    for key in ("PORT", "APP_PORT"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return "5000"


def _netloc(host: str) -> str:
    parsed = urlparse(host if "://" in host else f"//{host}")
    return parsed.netloc or host


def _hostname(host: str) -> str | None:
    parsed = urlparse(host if "://" in host else f"//{host}")
    return parsed.hostname


def _port(host: str) -> str | None:
    parsed = urlparse(host if "://" in host else f"//{host}")
    return str(parsed.port) if parsed.port else None


def _is_local_redirect_uri(uri: str) -> bool:
    parsed = urlparse(uri)
    return parsed.hostname in LOCAL_REDIRECT_HOSTS and parsed.path.rstrip("/") == "/login"
