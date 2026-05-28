"""Aba Fluxo Editorial — Kanban de status editorial + aprovação pelo dashboard."""
from __future__ import annotations
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, fmt_dt, PRIORITY_COLOR, PRIORITY_ICON, run_cli
from news_radar.dashboard_queries import update_editorial_status
from news_radar.repository import update_card_status
from news_radar.db import connect
from news_radar.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

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
view = st.radio("Visualização", ["Kanban compacto", "Lista detalhada", "Cards pendentes"], horizontal=True)
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
