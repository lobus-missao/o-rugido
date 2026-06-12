from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request

from news_radar.services.editorial import (
    apply_edit_and_refresh,
    edit_url_for,
    ensure_edit_token,
    get_dispatch,
    get_dispatch_by_token,
)
from news_radar.services.image_search import search_images

bp = Blueprint("edit", __name__)

_STATUS_LABEL = {
    "pending_article": "Aguardando aprovação do artigo",
    "article_approved": "Artigo aprovado, gerando card",
    "pending_card": "Aguardando aprovação do card",
    "card_approved": "Card aprovado",
    "ready_to_publish": "Pronto para publicar",
    "published": "Publicado",
    "article_rejected": "Artigo rejeitado",
    "card_rejected": "Card rejeitado",
}


def _build_view(dispatch: dict) -> dict:
    title = dispatch.get("edited_title") or dispatch.get("article_title") or ""
    summary = dispatch.get("edited_summary") or dispatch.get("article_summary") or ""
    image_url = dispatch.get("image_url") or ""
    status = dispatch.get("status") or ""
    return {
        "dispatch_id": dispatch["id"],
        "status": status,
        "status_label": _STATUS_LABEL.get(status, status),
        "title": title,
        "summary": summary,
        "image_url": image_url,
        "source": dispatch.get("article_source") or "",
        "article_url": dispatch.get("article_url") or "",
    }


@bp.route("/edit", methods=["GET", "POST"])
def edit_dispatch():
    token = (request.args.get("token") or "").strip()
    dispatch = get_dispatch_by_token(token)
    if not dispatch:
        return render_template("edit_invalid.html"), 404

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        summary = (request.form.get("summary") or "").strip()
        image_url = (request.form.get("image_url") or "").strip()
        result = apply_edit_and_refresh(
            dispatch_id=dispatch["id"],
            title=title or None,
            summary=summary or None,
            image_url=image_url or None,
            user="Editor",
        )
        dispatch = get_dispatch_by_token(token) or dispatch
        view = _build_view(dispatch)
        view["saved"] = True
        view["regenerated"] = bool(result.get("regenerated"))
        view["token"] = token
        return render_template(
            "edit.html", view=view, gallery=_initial_gallery(view["title"])
        )

    view = _build_view(dispatch)
    view["token"] = token
    return render_template(
        "edit.html", view=view, gallery=_initial_gallery(view["title"])
    )


def _initial_gallery(query: str, limit: int = 12) -> list[dict]:
    if not query:
        return []
    try:
        return search_images(query, limit=limit)
    except Exception:
        return []


@bp.get("/dispatch/<int:dispatch_id>/edit-token")
def get_edit_token(dispatch_id: int):
    """Retorna token + URL de edição para um dispatch (uso pelo n8n)."""
    if not get_dispatch(dispatch_id):
        return jsonify({"ok": False, "error": "dispatch nao encontrado"}), 404
    token = ensure_edit_token(dispatch_id)
    return jsonify({
        "ok": True,
        "dispatch_id": dispatch_id,
        "token": token,
        "edit_url": edit_url_for(dispatch_id),
    })
