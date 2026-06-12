from __future__ import annotations

from flask import Blueprint, jsonify, request

from news_radar.services.image_search import search_images

bp = Blueprint("images", __name__)


@bp.get("/api/image-search")
def image_search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"ok": False, "error": "parametro 'q' obrigatorio"}), 400

    try:
        limit = int(request.args.get("limit", 12))
    except ValueError:
        limit = 12
    limit = max(1, min(limit, 50))

    engines = request.args.get("engines") or None

    results = search_images(query, limit=limit, engines=engines)
    return jsonify({"ok": True, "query": query, "count": len(results), "results": results})
