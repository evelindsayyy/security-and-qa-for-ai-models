import os

from flask import Flask

from auth import register_auth
from dbutils.env import load_repo_env
from frontend.routes import register_routes


def create_app(test_config=None):
    load_repo_env()
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="templates",
        static_folder="static",
    )
    secret = os.environ.get("SECRET_KEY", "dev")
    trust_proxy = _trust_proxy_enabled()
    app.config.from_mapping(
        SECRET_KEY=secret,
        DATABASE=os.path.join(app.instance_path, "frontend.sqlite"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=trust_proxy,
        PREFERRED_URL_SCHEME="https" if trust_proxy else "http",
    )

    if test_config is None:
        app.config.from_pyfile("config.py", silent=True)
    else:
        app.config.from_mapping(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    register_auth(app)
    register_routes(app)

    # JSON API blueprint(s) under /api (Track A will add scans/safety here).
    # Lazy import keeps app composition free of any frontend<->api import cycle.
    from api import register_api

    register_api(app)

    if trust_proxy and not app.config.get("TESTING"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    if not app.config.get("TESTING"):
        from dbutils.startup import log_db_read_path
        from frontend import docker_launch

        log_db_read_path()
        docker_launch.warm_stacks_async()
    return app


def _trust_proxy_enabled() -> bool:
    if os.environ.get("TRUST_PROXY", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return bool(os.environ.get("CADDY_DOMAIN", "").strip())
