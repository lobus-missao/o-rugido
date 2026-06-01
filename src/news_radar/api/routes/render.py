from pathlib import Path

from flask import Blueprint, abort, jsonify, request, send_from_directory

from news_radar.core.config import CARDS_DIR
from news_radar.services.rendering import render_single_card

bp = Blueprint("render", __name__)


@bp.post("/cards/render")
def render_card():
    body = request.json or {}
    article_id = body.get("article_id")
    image_url = body.get("image_url") or None

    if not article_id:
        return jsonify({"ok": False, "error": "article_id obrigatorio"}), 400

    try:
        result = render_single_card(article_id, image_url=image_url)
    except LookupError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except FileNotFoundError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    if result.get("ok") and result.get("card_path"):
        filename = Path(result["card_path"]).name
        result["card_url"] = f"/cards/{filename}"

    status = 200 if result.get("ok") else 502
    return jsonify(result), status


@bp.get("/cards/<filename>")
def serve_card(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        abort(400)
    if not filename.endswith(".png"):
        abort(404)
    return send_from_directory(CARDS_DIR, filename, mimetype="image/png")
