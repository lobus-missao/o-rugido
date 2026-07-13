from __future__ import annotations

from pathlib import Path

from flask import Flask

ROOT = Path(__file__).resolve().parents[3]
WEB_TEMPLATES_DIR = ROOT / "templates" / "web"


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(WEB_TEMPLATES_DIR))

    from .routes.edit import bp as edit_bp
    from .routes.health import bp as health_bp
    from .routes.images import bp as images_bp
    from .routes.ingestion import bp as ingestion_bp
    from .routes.monitor import bp as monitor_bp
    from .routes.render import bp as render_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(ingestion_bp)
    app.register_blueprint(render_bp)
    app.register_blueprint(images_bp)
    app.register_blueprint(edit_bp)
    app.register_blueprint(monitor_bp)

    return app
