"""Duke OIDC client configuration (Authlib)."""

from __future__ import annotations

import os

from authlib.integrations.flask_client import OAuth

from dbutils.env import load_repo_env

DUKE_OIDC_DISCOVERY = "https://oauth.oit.duke.edu/oidc/.well-known/openid-configuration"
DUKE_OIDC_SCOPES = "openid profile email"

oauth = OAuth()


def init_oauth(app) -> None:
    load_repo_env()
    client_id = os.environ.get("DUKE_OIDC_CLIENT_ID", "").strip()
    client_secret = os.environ.get("DUKE_OIDC_CLIENT_SECRET", "").strip()
    if not client_id:
        return
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
    if uri:
        return uri
    return "http://127.0.0.1:5000/auth/callback"
