from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify

ROOT = Path(__file__).resolve().parents[3]
CLI = [sys.executable, "-m", "news_radar.cli"]
WEB_TEMPLATES_DIR = ROOT / "templates" / "web"


def run_cli(*args, timeout: int = 300) -> tuple[dict, int]:
    r = subprocess.run(
        CLI + list(args),
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=timeout,
    )
    if r.returncode == 0:
        try:
            parsed = json.loads(r.stdout)
            if isinstance(parsed, dict):
                return {"ok": True, **parsed}, 200
            return {"ok": True, "data": parsed}, 200
        except Exception:
            return {"ok": True, "output": r.stdout.strip()[:500]}, 200
    return {"ok": False, "error": r.stderr.strip()[-500:]}, 500


def cli_json(*args, timeout: int = 300):
    payload, status = run_cli(*args, timeout=timeout)
    return jsonify(payload), status


def create_app() -> Flask:
    app = Flask(__name__, template_folder=str(WEB_TEMPLATES_DIR))

    from .routes.edit import bp as edit_bp
    from .routes.health import bp as health_bp
    from .routes.images import bp as images_bp
    from .routes.ingestion import bp as ingestion_bp
    from .routes.render import bp as render_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(ingestion_bp)
    app.register_blueprint(render_bp)
    app.register_blueprint(images_bp)
    app.register_blueprint(edit_bp)

    return app
