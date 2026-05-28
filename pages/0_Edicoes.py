"""
Página Edições — central de controle das 3 postagens diárias.
Controla o fluxo: selecionar → aprovar artigo → aprovar card → publicar.
"""
from __future__ import annotations
import sys, json
from datetime import date, datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, run_cli, fmt_dt, PRIORITY_ICON, PRIORITY_COLOR
from news_radar.dispatch import (
    EDITIONS, get_today_editions, get_edition_dispatches,
    approve_article, reject_article, approve_card, reject_card,
    regenerate_card, mark_published, create_dispatch, select_top_articles,
)
from news_radar.db import connect

st.set_page_config(page_title="Edições · News Radar", page_icon="📰", layout="wide")
sidebar_controls()
st.title("📰 Edições do Dia")

# ── Cabeçalho com horários ────────────────────────────────────────────────────
now = datetime.now()
st.caption(f"Agora: {now.strftime('%H:%M')} · {date.today().strftime('%d/%m/%Y')}")

st.info(
    "**Ciclo editorial:** n8n dispara automaticamente 30min antes de cada postagem. "
    "Você aprova os artigos → o sistema gera o card → você aprova o card → pronto para publicar."
)

STATUS_ICON = {
    "pending_article":  "⏳",
    "article_approved": "✅",
    "article_rejected": "❌",
    "pending_card":     "🖼️",
    "card_approved":    "✅✅",
    "ready_to_publish": "✅✅",
    "card_rejected":    "❌🖼️",
    "published":        "📣",
}
STATUS_LABEL = {
    "pending_article":  "Aguardando aprovação",
    "article_approved": "Artigo aprovado · gerando card",
    "article_rejected": "Rejeitado",
    "pending_card":     "Card aguardando aprovação",
    "card_approved":    "Pronto para publicar!",
    "ready_to_publish": "Pronto para publicar!",
    "card_rejected":    "Card rejeitado",
    "published":        "Publicado ✓",
}

today = date.today()
scope_ed = st.selectbox("Escopo", ["brasil", "piaui", "teresina"],
                         key="edicoes_scope")

# ── 3 edições ─────────────────────────────────────────────────────────────────
for edition_key, edition_info in EDITIONS.items():
    label = edition_info["label"]
    dispatch_hour = edition_info["dispatch_hour"]
    dispatch_min = edition_info["dispatch_min"]
    post_hour = edition_info["post_hour"]

    dispatches = get_edition_dispatches(edition_key, today)
    has_dispatches = bool(dispatches)

    # Status geral da edição
    if not has_dispatches:
        edition_status = "🔘 Não disparado"
        status_color = "#94a3b8"
    elif all(d.get("status") == "published" for d in dispatches):
        edition_status = "📣 Publicado"
        status_color = "#16a34a"
    elif any(d.get("status") in ("card_approved", "ready_to_publish") for d in dispatches):
        edition_status = "✅ Pronto para publicar"
        status_color = "#2563eb"
    elif any(d.get("status") == "pending_card" for d in dispatches):
        edition_status = "🖼️ Aprovando cards"
        status_color = "#d97706"
    elif any(d.get("status") == "pending_article" for d in dispatches):
        edition_status = "⏳ Aguardando aprovação"
        status_color = "#ea580c"
    else:
        edition_status = "✅ Em andamento"
        status_color = "#475569"

    st.markdown(
        f'<div style="border-left:4px solid {status_color};padding:8px 14px;margin:10px 0;">'
        f'<span style="font-size:18px;font-weight:700;">{label}</span>&nbsp;&nbsp;'
        f'<span style="color:{status_color};font-size:13px;">{edition_status}</span>&nbsp;&nbsp;'
        f'<span style="color:#94a3b8;font-size:12px;">Disparo: {dispatch_hour:02d}:{dispatch_min:02d} · Postagem: {post_hour:02d}:00</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Disparo manual
    col_disp, col_prev = st.columns([1, 3])
    with col_disp:
        if not has_dispatches:
            if st.button(f"⚡ Disparar agora", key=f"dispatch_{edition_key}"):
                with st.spinner(f"Selecionando e enviando top 3..."):
                    try:
                        created = create_dispatch(edition=edition_key, scope=scope_ed, top=3)
                        if created:
                            st.success(f"✅ {len(created)} artigo(s) enviados ao Telegram!")
                            st.rerun()
                        else:
                            st.warning("Nenhum artigo disponível no período.")
                    except Exception as e:
                        st.error(f"Erro: {e}")
        else:
            # Mostra preview dos artigos que seriam selecionados
            if st.button(f"👁 Preview seleção", key=f"preview_{edition_key}"):
                st.session_state[f"show_preview_{edition_key}"] = True

    with col_prev:
        if st.session_state.get(f"show_preview_{edition_key}"):
            try:
                candidates = select_top_articles(edition_key, scope=scope_ed, top=5)
                if candidates:
                    st.markdown("**Artigos que seriam selecionados:**")
                    for i, a in enumerate(candidates[:5], 1):
                        score = float(a.get(f"final_score_{scope_ed}") or 0)
                        p = a.get("priority") or ""
                        st.markdown(f"{i}. {PRIORITY_ICON.get(p,'⚪')} {a.get('title','')[:60]} · ★{score:.0f}")
                else:
                    st.info("Sem artigos disponíveis no período.")
            except Exception as e:
                st.error(str(e))

    # ── Artigos da edição ─────────────────────────────────────────────────────
    if has_dispatches:
        for d in dispatches:
            status = d.get("status", "")
            rank = d.get("rank", "?")
            dispatch_id = d.get("id")
            title = d.get("title") or ""
            source = d.get("source") or ""
            score = float(d.get(f"final_score_{scope_ed}") or d.get("final_score_brasil") or 0)
            priority = d.get("priority") or ""
            card_path = d.get("card_path") or ""
            status_icon = STATUS_ICON.get(status, "❓")
            status_label = STATUS_LABEL.get(status, status)

            with st.container():
                col_rank, col_info, col_actions = st.columns([1, 4, 2])

                with col_rank:
                    st.markdown(f"### #{rank}")
                    st.caption(status_icon)

                with col_info:
                    color = PRIORITY_COLOR.get(priority, "#6b7280")
                    st.markdown(
                        f'<span style="color:{color};font-weight:700;">'
                        f'{PRIORITY_ICON.get(priority,"⚪")} {priority.upper()}</span> · '
                        f'★{score:.0f} · {source}',
                        unsafe_allow_html=True,
                    )
                    url = d.get("canonical_url") or ""
                    if url:
                        st.markdown(f"**[{title[:80]}]({url})**")
                    else:
                        st.markdown(f"**{title[:80]}**")
                    st.caption(f"{status_label} · {fmt_dt(d.get('published_at'), 16)}")

                    # Card preview
                    if card_path and Path(card_path).exists():
                        st.image(card_path, width=280)

                with col_actions:
                    # Ações por status
                    if status == "pending_article":
                        if st.button("✅ Aprovar artigo", key=f"app_art_{dispatch_id}", type="primary"):
                            with st.spinner("Aprovando e gerando card..."):
                                try:
                                    approve_article(dispatch_id, "Editor (Dashboard)")
                                    st.success("Artigo aprovado! Card sendo gerado...")
                                    st.rerun()
                                except Exception as e:
                                    st.error(str(e))
                        if st.button("❌ Rejeitar", key=f"rej_art_{dispatch_id}"):
                            reject_article(dispatch_id, "Editor (Dashboard)")
                            st.rerun()

                    elif status == "article_approved":
                        st.info("Gerando card... aguarde.")
                        if st.button("🔄 Tentar regerar card", key=f"regen_{dispatch_id}"):
                            try:
                                regenerate_card(dispatch_id, "Editor (Dashboard)")
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

                    elif status == "pending_card":
                        if st.button("✅ Aprovar card", key=f"app_card_{dispatch_id}", type="primary"):
                            approve_card(dispatch_id, "Editor (Dashboard)")
                            st.success("Card aprovado! Pronto para publicar.")
                            st.rerun()
                        if st.button("🔄 Regerar card", key=f"regen2_{dispatch_id}"):
                            with st.spinner("Regerando..."):
                                try:
                                    regenerate_card(dispatch_id, "Editor (Dashboard)")
                                    st.rerun()
                                except Exception as e:
                                    st.error(str(e))
                        if st.button("❌ Rejeitar card", key=f"rej_card_{dispatch_id}"):
                            reject_card(dispatch_id, "Editor (Dashboard)")
                            st.rerun()

                    elif status in ("card_approved", "ready_to_publish"):
                        st.success("✅ Pronto para publicar!")
                        if st.button("📣 Marcar como publicado", key=f"pub_{dispatch_id}", type="primary"):
                            mark_published(dispatch_id)
                            st.rerun()

                    elif status == "published":
                        st.success("📣 Publicado!")

                    elif status in ("article_rejected", "card_rejected"):
                        st.error(f"{'Artigo' if 'article' in status else 'Card'} rejeitado.")

            st.divider()

    st.markdown("---")

# ── Histórico de edições passadas ─────────────────────────────────────────────
with st.expander("📅 Histórico de edições"):
    days_back = st.slider("Dias atrás", 1, 30, 7, key="hist_days")
    from datetime import timedelta
    try:
        with connect() as conn:
            with conn.cursor() as cur:
                cutoff = date.today() - timedelta(days=days_back)
                cur.execute("""
                    SELECT d.id, d.edition, d.edition_date, d.rank, d.status,
                           a.title, a.source, d.scope
                    FROM dispatches d
                    JOIN articles a ON d.article_id = a.id
                    WHERE d.edition_date >= %s
                    ORDER BY d.edition_date DESC, d.edition, d.rank
                """, (cutoff,))
                rows = [dict(r) for r in cur.fetchall()]

        if rows:
            import pandas as pd
            df = pd.DataFrame(rows)
            df["edition_date"] = df["edition_date"].astype(str)
            df["title"] = df["title"].str[:50]
            st.dataframe(df[["edition_date", "edition", "rank", "status", "title", "source"]],
                         use_container_width=True)
        else:
            st.info("Sem histórico no período.")
    except Exception as e:
        st.error(f"Erro: {e}")
