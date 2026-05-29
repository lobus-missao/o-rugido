"""Aba Fluxo Editorial — Kanban de status editorial + geração de cards."""
from __future__ import annotations
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
import streamlit.components.v1 as components
from news_radar.dash_utils import sidebar_controls, fmt_dt, PRIORITY_COLOR, PRIORITY_ICON, run_cli
from news_radar.dashboard_queries import update_editorial_status
from news_radar.repository import update_card_status
from news_radar.db import connect
from news_radar.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from news_radar.card_renderer import (
    build_card_context,
    render_card_html,
    save_card_html,
    is_playwright_available,
    list_templates,
    render_cards,
)
from news_radar.editorial import record_editorial_action

st.set_page_config(page_title="Editorial · News Radar", page_icon="📋", layout="wide")
sidebar_controls()
st.title("📋 Fluxo Editorial")

KANBAN_COLS = [
    ("discovered",      "🔍 Descoberto"),
    ("needs_ai",        "🤖 Precisa de IA"),
    ("ai_done",         "✅ IA pronta"),
    ("selected",        "🎯 Selecionado"),
    ("card_generated",  "🖼️ Card gerado"),
    ("sent_to_telegram","📤 Enviado"),
    ("approved",        "✅ Aprovado"),
    ("ready_to_publish","✅ Pronto"),
    ("rejected",        "❌ Rejeitado"),
    ("published",       "📣 Publicado"),
    ("archived",        "📦 Arquivado"),
]
STATUS_NEXT = {
    "discovered": "needs_ai",
    "needs_ai": "ai_done",
    "ai_done": "selected",
    "selected": "card_generated",
    "card_generated": "sent_to_telegram",
    "sent_to_telegram": "approved",
    "approved": "ready_to_publish",
    "ready_to_publish": "published",
}
STATUS_PREV_OR_REJECT = {
    "selected": "rejected",
    "card_generated": "rejected",
    "sent_to_telegram": "rejected",
    "approved": "rejected",
    "ready_to_publish": "rejected",
}

# ── Modo de visualização ───────────────────────────────────────────────────────
view = st.radio(
    "Visualização",
    ["Kanban compacto", "Lista detalhada", "Cards pendentes", "Gerar Card"],
    horizontal=True,
)
scope_ed = st.selectbox("Escopo", ["brasil", "piaui", "teresina"], key="ed_scope")
score_col = f"final_score_{scope_ed}"

telegram_ok = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)

# ── Carrega artigos por status ─────────────────────────────────────────────────
def load_by_status(status_list: list[str], limit: int = 20) -> dict[str, list[dict]]:
    ph = ",".join(["%s"] * len(status_list))
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT * FROM articles
                    WHERE editorial_status IN ({ph})
                    ORDER BY {score_col} DESC, published_at DESC NULLS LAST
                    LIMIT %s
                    """,
                    status_list + [limit * len(status_list)],
                )
                rows = [dict(r) for r in cur.fetchall()]
        result = {s: [] for s in status_list}
        for r in rows:
            es = r.get("editorial_status") or "discovered"
            if es in result and len(result[es]) < limit:
                result[es].append(r)
        return result
    except Exception as e:
        st.error(f"Erro: {e}")
        return {s: [] for s in status_list}


if view == "Kanban compacto":
    all_statuses = [s for s, _ in KANBAN_COLS]
    data = load_by_status(all_statuses, limit=10)

    # Mostra só colunas com artigos ou as 5 principais
    active = [(s, l) for s, l in KANBAN_COLS if data.get(s)]
    if not active:
        active = KANBAN_COLS[:5]

    for i in range(0, len(active), 3):
        chunk = active[i:i+3]
        cols = st.columns(len(chunk))
        for col, (status, label) in zip(cols, chunk):
            arts = data.get(status, [])
            with col:
                st.markdown(f"**{label}** `{len(arts)}`")
                for art in arts[:5]:
                    p = art.get("priority") or ""
                    s = float(art.get(score_col) or 0)
                    title = art.get("title") or ""
                    art_id = art.get("id", "")

                    with st.container():
                        st.markdown(
                            f'{PRIORITY_ICON.get(p,"⚪")} **{title[:45]}**  \n'
                            f'<small>{art.get("source","")[:20]} · ★{s:.0f}</small>',
                            unsafe_allow_html=True,
                        )
                        next_s = STATUS_NEXT.get(status)
                        rej_s = STATUS_PREV_OR_REJECT.get(status)
                        btn_cols = st.columns(2 if (next_s and rej_s) else 1)
                        if next_s:
                            with btn_cols[0]:
                                if st.button("→", key=f"k_next_{art_id[:8]}_{status}", help=f"Mover para {next_s}"):
                                    update_editorial_status(art_id, next_s)
                                    st.rerun()
                        if rej_s:
                            with btn_cols[-1]:
                                if st.button("✕", key=f"k_rej_{art_id[:8]}_{status}", help="Rejeitar"):
                                    update_editorial_status(art_id, rej_s)
                                    st.rerun()
                        st.divider()

elif view == "Lista detalhada":
    status_filter = st.multiselect("Status", [s for s, _ in KANBAN_COLS],
                                   default=["selected", "ai_done", "card_generated", "sent_to_telegram"],
                                   format_func=lambda s: next((l for ss, l in KANBAN_COLS if ss == s), s))
    data = load_by_status(status_filter or [s for s, _ in KANBAN_COLS], limit=15)

    for status, label in KANBAN_COLS:
        arts = data.get(status, [])
        if not arts or status not in (status_filter or [s for s, _ in KANBAN_COLS]):
            continue
        with st.expander(f"{label} — {len(arts)} artigo(s)", expanded=True):
            for art in arts:
                p = art.get("priority") or ""
                s = float(art.get(score_col) or 0)
                art_id = art.get("id", "")
                title = art.get("title") or ""
                has_ai = bool(art.get("ai_score"))
                card_st = art.get("card_status") or "none"

                col_t, col_a = st.columns([3, 1])
                with col_t:
                    st.markdown(f"{PRIORITY_ICON.get(p,'⚪')} **{title[:70]}**")
                    st.caption(f"{art.get('source','')} · ★{s:.0f} · {'🤖 IA' if has_ai else '📊 Auto'} · card: {card_st}")
                with col_a:
                    action_cols = st.columns(3)
                    next_s = STATUS_NEXT.get(status)
                    if next_s:
                        with action_cols[0]:
                            if st.button("→", key=f"ld_next_{art_id[:8]}", help=next_s):
                                update_editorial_status(art_id, next_s)
                                st.rerun()
                    with action_cols[1]:
                        if st.button("❌", key=f"ld_rej_{art_id[:8]}", help="Rejeitar"):
                            update_editorial_status(art_id, "rejected")
                            st.rerun()
                    with action_cols[2]:
                        if st.button("📦", key=f"ld_arch_{art_id[:8]}", help="Arquivar"):
                            update_editorial_status(art_id, "archived")
                            st.rerun()

elif view == "Cards pendentes":
    st.subheader("Aprovação de Cards — Diretamente no Dashboard")

    if not telegram_ok:
        st.warning("⚠️ Telegram não configurado. Adicione TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env")

    # Artigos com card pendente
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT * FROM articles
                    WHERE card_status IN ('none', 'pending')
                      AND priority IN ('alta', 'critica')
                    ORDER BY final_score_brasil DESC LIMIT 20
                """)
                candidates = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        candidates = []
        st.error(f"Erro: {e}")

    if not candidates:
        st.info("Nenhum artigo com prioridade alta/crítica aguardando card.")
    else:
        for art in candidates:
            p = art.get("priority") or ""
            s = float(art.get(score_col) or 0)
            art_id = art.get("id", "")
            card_st = art.get("card_status") or "none"
            card_path = art.get("card_path") or ""

            ai_json = art.get("ai_json") or {}
            if isinstance(ai_json, str):
                try: ai_json = json.loads(ai_json)
                except: ai_json = {}

            with st.expander(
                f"{PRIORITY_ICON.get(p,'⚪')} [{p.upper()}] {art.get('title','')[:70]} · ★{s:.0f} · card: {card_st}",
                expanded=card_st == "none"
            ):
                col_img, col_info = st.columns([2, 1])

                with col_img:
                    if card_path and Path(card_path).exists():
                        st.image(card_path, use_container_width=True)
                    else:
                        st.info("Card não gerado ainda.")

                    # Preview do resumo da IA
                    resumo = ai_json.get("resumo_curto") or (art.get("summary") or "")[:150]
                    if resumo:
                        st.caption(resumo)

                with col_info:
                    st.markdown(f"**Fonte:** {art.get('source','')}")
                    st.markdown(f"**Score:** {s:.1f}")
                    locality = art.get("locality") or ai_json.get("localidade") or ""
                    if locality:
                        st.markdown(f"📍 {locality}")

                    btn1, btn2 = st.columns(2)

                    with btn1:
                        if card_st == "none":
                            if st.button("🖼️ Gerar card", key=f"gen_{art_id[:8]}"):
                                with st.spinner("Gerando..."):
                                    r = run_cli("make-card", "--scope", scope_ed, "--limit", "1", timeout=30)
                                st.success("Card gerado!") if r["ok"] else st.error(r.get("error",""))
                                st.rerun()
                        else:
                            # Aprovação direta pelo dashboard
                            if st.button("✅ Aprovar", key=f"app_{art_id[:8]}", type="primary"):
                                update_card_status(art_id, "approved")
                                update_editorial_status(art_id, "approved")
                                st.success("Aprovado!")
                                st.rerun()

                    with btn2:
                        if card_st in ("pending", "none") and telegram_ok and card_path and Path(card_path).exists():
                            if st.button("📤 Telegram", key=f"tg_{art_id[:8]}"):
                                r = run_cli("send-card-telegram", "--article-id", art_id, timeout=15)
                                st.success("Enviado!") if r["ok"] else st.error(r.get("error",""))
                                st.rerun()
                        if card_st == "pending":
                            if st.button("❌ Rejeitar", key=f"rej_{art_id[:8]}"):
                                update_card_status(art_id, "rejected")
                                update_editorial_status(art_id, "rejected")
                                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# VIEW: Gerar Card — seleção, edição editorial e preview antes de gerar
# ══════════════════════════════════════════════════════════════════════════════
elif view == "Gerar Card":
    st.subheader("Geração de Card Editorial")

    # ── Verificar Playwright ──────────────────────────────────────────────────
    playwright_ok = is_playwright_available()
    if not playwright_ok:
        st.warning(
            "Playwright/Chromium não detectado — apenas preview HTML disponível. "
            "Para gerar PNG execute: `playwright install chromium`"
        )

    # ── Escolha da fonte de dados ─────────────────────────────────────────────
    fonte_tipo = st.radio(
        "Origem dos dados",
        ["Artigo", "Cluster"],
        horizontal=True,
        key="card_gen_fonte",
    )

    # ── Carrega artigos candidatos ────────────────────────────────────────────
    def _load_card_candidates(limit: int = 50) -> list[dict]:
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        SELECT * FROM articles
                        WHERE {score_col} > 0
                          AND editorial_status NOT IN ('rejected', 'archived', 'published')
                        ORDER BY {score_col} DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            st.error(f"Erro ao carregar artigos: {e}")
            return []

    def _load_active_clusters(limit: int = 30) -> list[dict]:
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT sc.*,
                               (SELECT ca.article_id FROM cluster_articles ca
                                WHERE ca.cluster_id = sc.id AND ca.is_primary = TRUE
                                LIMIT 1) AS primary_article_id
                        FROM story_clusters sc
                        WHERE sc.status = 'active'
                        ORDER BY sc.cluster_score DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            st.error(f"Erro ao carregar clusters: {e}")
            return []

    article_sel: dict | None = None

    if fonte_tipo == "Artigo":
        candidates = _load_card_candidates()
        if not candidates:
            st.info("Nenhum artigo disponível para gerar card.")
        else:
            options = {
                f"{PRIORITY_ICON.get(a.get('priority',''),'⚪')} [{a.get('priority','?').upper()}] "
                f"{a.get('title','')[:60]} · ★{float(a.get(score_col) or 0):.0f}": a
                for a in candidates
            }
            sel_label = st.selectbox(
                "Selecionar artigo",
                list(options.keys()),
                key="card_gen_art_sel",
            )
            article_sel = options[sel_label]

    else:  # Cluster
        clusters = _load_active_clusters()
        if not clusters:
            st.info("Nenhum cluster ativo encontrado.")
        else:
            options_c = {
                f"[{c.get('cluster_type','?')}] {c.get('title','')[:60]} "
                f"· {c.get('article_count', 0)} art. · ★{float(c.get('cluster_score') or 0):.0f}": c
                for c in clusters
            }
            sel_label_c = st.selectbox(
                "Selecionar cluster",
                list(options_c.keys()),
                key="card_gen_cluster_sel",
            )
            cluster_sel = options_c[sel_label_c]

            # Carrega artigo primário do cluster
            primary_id = cluster_sel.get("primary_article_id")
            if primary_id:
                try:
                    with connect() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "SELECT * FROM articles WHERE id = %s", (primary_id,)
                            )
                            row = cur.fetchone()
                            article_sel = dict(row) if row else None
                except Exception:
                    article_sel = None

            if not article_sel:
                # Fallback: primeiro artigo do cluster por score
                try:
                    with connect() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                f"""
                                SELECT a.* FROM articles a
                                JOIN cluster_articles ca ON ca.article_id = a.id
                                WHERE ca.cluster_id = %s
                                ORDER BY a.{score_col} DESC NULLS LAST
                                LIMIT 1
                                """,
                                (cluster_sel["id"],),
                            )
                            row = cur.fetchone()
                            article_sel = dict(row) if row else None
                except Exception:
                    pass

            if article_sel:
                # Usa o título do cluster como título sugerido
                if not article_sel.get("ai_json"):
                    article_sel = dict(article_sel)
                else:
                    ai_j = article_sel.get("ai_json") or {}
                    if isinstance(ai_j, str):
                        try:
                            ai_j = json.loads(ai_j)
                        except Exception:
                            ai_j = {}
                    ai_j["titulo_sugerido"] = ai_j.get("titulo_sugerido") or cluster_sel.get("title", "")
                    article_sel = {**article_sel, "ai_json": ai_j}
            else:
                st.warning("Cluster sem artigos associados.")

    # ── Painel de edição e geração ────────────────────────────────────────────
    if article_sel:
        ai_j = article_sel.get("ai_json") or {}
        if isinstance(ai_j, str):
            try:
                ai_j = json.loads(ai_j)
            except Exception:
                ai_j = {}

        st.divider()
        col_edit, col_meta = st.columns([3, 1])

        with col_meta:
            st.markdown("**Metadados**")
            st.caption(f"Fonte: {article_sel.get('source','')}")
            st.caption(f"Data: {str(article_sel.get('published_at',''))[:10]}")
            st.caption(f"Escopo: {article_sel.get('source_scope','')}")
            score_val = float(article_sel.get(score_col) or 0)
            st.caption(f"Score ({scope_ed}): {score_val:.1f}")
            priority_val = article_sel.get("priority") or "-"
            picon = PRIORITY_ICON.get(priority_val, "⚪")
            st.caption(f"Prioridade: {picon} {priority_val.upper()}")
            has_ai = bool(article_sel.get("ai_score"))
            st.caption(f"IA: {'Sim' if has_ai else 'Não'}")

        with col_edit:
            titulo_sug = ai_j.get("titulo_sugerido") or article_sel.get("title") or ""
            subtitulo_sug = ai_j.get("subtitulo_sugerido") or ""

            titulo_edit = st.text_input(
                "Título do card",
                value=titulo_sug,
                key="card_gen_titulo",
                help="Editável antes de gerar. Padrão: titulo_sugerido da IA ou título original.",
            )
            subtitulo_edit = st.text_input(
                "Subtítulo (opcional)",
                value=subtitulo_sug,
                key="card_gen_subtitulo",
                help="Editável antes de gerar. Padrão: subtitulo_sugerido da IA.",
            )

            templates_avail = list_templates()
            template_sel = st.selectbox(
                "Template",
                templates_avail,
                key="card_gen_template",
            )

        # ── Botões de ação ────────────────────────────────────────────────────
        st.divider()
        btn_preview, btn_gerar = st.columns(2)

        with btn_preview:
            if st.button("👁 Preview HTML", key="card_gen_preview", use_container_width=True):
                if not titulo_edit.strip():
                    st.error("Título obrigatório para gerar preview.")
                else:
                    try:
                        html_preview = render_card_html(
                            article_sel,
                            template_name=template_sel,
                            scope=scope_ed,
                            title_override=titulo_edit.strip() or None,
                            subtitle_override=subtitulo_edit.strip() or None,
                        )
                        st.session_state["card_gen_html"] = html_preview
                        st.session_state["card_gen_article"] = article_sel
                        st.session_state["card_gen_titulo_final"] = titulo_edit.strip()
                        st.session_state["card_gen_subtitulo_final"] = subtitulo_edit.strip()
                        st.session_state["card_gen_template_final"] = template_sel
                        st.success("Preview gerado.")
                    except Exception as e:
                        st.error(f"Erro ao renderizar: {e}")

        with btn_gerar:
            if st.button(
                "🖼 Gerar Card" + (" + PNG" if playwright_ok else " (HTML)"),
                key="card_gen_gerar",
                type="primary",
                use_container_width=True,
            ):
                if not titulo_edit.strip():
                    st.error("Título obrigatório para gerar card.")
                else:
                    art_id_g = article_sel["id"]
                    try:
                        html_final = render_card_html(
                            article_sel,
                            template_name=template_sel,
                            scope=scope_ed,
                            title_override=titulo_edit.strip() or None,
                            subtitle_override=subtitulo_edit.strip() or None,
                        )
                        html_path = save_card_html(art_id_g, html_final)
                        update_card_status(art_id_g, status="pending", html_path=str(html_path))

                        png_path: str | None = None
                        if playwright_ok:
                            with st.spinner("Gerando PNG via Playwright..."):
                                try:
                                    cards = render_cards(
                                        article_ids=[art_id_g],
                                        template_name=template_sel,
                                        scope=scope_ed,
                                    )
                                    if cards and cards[0].get("card_path"):
                                        png_path = cards[0]["card_path"]
                                except Exception as e_pw:
                                    st.warning(f"Playwright falhou: {e_pw}")

                        # Registrar ação editorial
                        try:
                            record_editorial_action(
                                action="card_generated",
                                actor="Editor",
                                article_id=art_id_g,
                                metadata={
                                    "template": template_sel,
                                    "titulo_editado": titulo_edit.strip(),
                                    "subtitulo_editado": subtitulo_edit.strip(),
                                    "html_path": str(html_path),
                                    "png_path": png_path,
                                    "playwright": playwright_ok,
                                },
                            )
                        except Exception:
                            pass

                        st.session_state["card_gen_html"] = html_final
                        st.session_state["card_gen_png"] = png_path
                        st.session_state["card_gen_html_path"] = str(html_path)

                        if png_path:
                            st.success(f"Card PNG gerado: `{png_path}`")
                        else:
                            st.success(f"Card HTML salvo: `{html_path}`")

                        st.rerun()

                    except Exception as e:
                        st.error(f"Erro ao gerar card: {e}")

        # ── Mostrar preview HTML se disponível ────────────────────────────────
        if "card_gen_html" in st.session_state:
            st.divider()
            st.markdown("**Preview do Card**")

            # Mostrar PNG se existir
            png_stored = st.session_state.get("card_gen_png")
            if png_stored and Path(png_stored).exists():
                st.image(png_stored, caption="Card PNG gerado", use_container_width=False)
            else:
                components.html(
                    st.session_state["card_gen_html"],
                    height=620,
                    scrolling=True,
                )

            html_stored = st.session_state.get("card_gen_html_path")
            if html_stored:
                st.caption(f"HTML salvo em: `{html_stored}`")

            if st.button("Limpar preview", key="card_gen_clear"):
                for k in ["card_gen_html", "card_gen_png", "card_gen_html_path",
                           "card_gen_article", "card_gen_titulo_final",
                           "card_gen_subtitulo_final", "card_gen_template_final"]:
                    st.session_state.pop(k, None)
                st.rerun()
