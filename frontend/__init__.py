import os

from flask import Flask

from frontend.routes import register_routes


def create_app(test_config=None):
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="templates",
        static_folder="static",
    )
    app.config.from_mapping(
        SECRET_KEY="dev",
        DATABASE=os.path.join(app.instance_path, "frontend.sqlite"),
    )

    if test_config is None:
        app.config.from_pyfile("config.py", silent=True)
    else:
        app.config.from_mapping(test_config)

    os.makedirs(app.instance_path, exist_ok=True)
    register_routes(app)

    # JSON API blueprint(s) under /api (Track A will add scans/safety here).
    # Lazy import keeps app composition free of any frontend<->api import cycle.
    from api import register_api

    register_api(app)

    if not app.config.get("TESTING"):
        from dbutils.startup import log_db_read_path
        from frontend import docker_launch

        log_db_read_path()
        docker_launch.warm_stacks_async()
    return app
