"""Página de Auditoria Editorial — histórico de ações, filtros e métricas."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
import pandas as pd
from news_radar.dash_utils import sidebar_controls, fmt_dt
from news_radar.dashboard_queries import (
    audit_page_actions,
    audit_metrics,
    article_audit_history,
)

st.set_page_config(
    page_title="Auditoria · News Radar",
    page_icon="🔍",
    layout="wide",
)
sidebar_controls()
st.title("🔍 Auditoria Editorial")

# ── Filtros ───────────────────────────────────────────────────────────────────
st.markdown("### Filtros")
col1, col2, col3, col4 = st.columns(4)

with col1:
    days_back = st.selectbox("Período", [1, 3, 7, 14, 30], index=2, format_func=lambda d: f"Últimos {d} dia(s)")

with col2:
    ACTION_OPTIONS = [
        "", "approve_article", "reject_article", "approve_card",
        "reject_card", "published", "card_generated", "ai_import",
        "status_change",
    ]
    action_filter = st.selectbox(
        "Tipo de ação",
        ACTION_OPTIONS,
        format_func=lambda x: x if x else "Todas",
    )

with col3:
    actor_filter = st.text_input("Ator (parcial)", placeholder="Editor, system…")

with col4:
    limit = st.selectbox("Limite", [50, 100, 200, 500], index=1)

st.divider()

# ── Métricas ──────────────────────────────────────────────────────────────────
try:
    metrics = audit_metrics(days_back=days_back)
except Exception as e:
    metrics = {"total": 0, "by_action": {}, "by_actor": {}, "approvals": 0, "rejections": 0}
    st.error(f"Erro ao carregar métricas: {e}")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total de ações", metrics["total"])
m2.metric("Aprovações", metrics["approvals"])
m3.metric("Rejeições", metrics["rejections"])
m4.metric("Publicações", metrics["by_action"].get("published", 0))

if metrics["by_action"]:
    with st.expander("Distribuição por tipo de ação", expanded=False):
        col_act, col_actor = st.columns(2)
        with col_act:
            st.markdown("**Por ação**")
            for act, cnt in sorted(metrics["by_action"].items(), key=lambda x: -x[1]):
                st.markdown(f"- `{act}` — **{cnt}**")
        with col_actor:
            st.markdown("**Por ator**")
            for actor, cnt in sorted(metrics["by_actor"].items(), key=lambda x: -x[1]):
                st.markdown(f"- {actor} — **{cnt}**")

st.divider()

# ── Tabela de ações ───────────────────────────────────────────────────────────
st.markdown("### Histórico de Ações")

try:
    rows = audit_page_actions(
        days_back=days_back,
        action_filter=action_filter or None,
        actor_filter=actor_filter or None,
        limit=limit,
    )
except Exception as e:
    rows = []
    st.error(f"Erro ao carregar histórico: {e}")

if not rows:
    st.info("Nenhuma ação registrada no período com os filtros selecionados.")
else:
    ACTION_ICON = {
        "approve_article": "✅",
        "reject_article": "❌",
        "approve_card": "✅🖼",
        "reject_card": "❌🖼",
        "published": "📣",
        "card_generated": "🖼",
        "ai_import": "🤖",
        "status_change": "🔄",
    }

    st.caption(f"{len(rows)} ação(ões) encontrada(s)")

    for row in rows:
        action = row.get("action") or ""
        icon = ACTION_ICON.get(action, "·")
        actor = row.get("actor") or "sistema"
        art_title = row.get("article_title") or "(sem artigo)"
        from_s = row.get("from_status") or ""
        to_s = row.get("to_status") or ""
        notes = row.get("notes") or ""
        ts = fmt_dt(row.get("created_at"), 16)
        dispatch_id = row.get("dispatch_id")

        col_icon, col_main, col_meta = st.columns([1, 6, 3])

        with col_icon:
            st.markdown(f"### {icon}")

        with col_main:
            st.markdown(f"**{action}** por `{actor}`")
            st.caption(f"📰 {art_title[:70]}")
            if from_s or to_s:
                st.caption(f"Status: `{from_s}` → `{to_s}`")
            if notes:
                st.caption(f"💬 {notes}")

        with col_meta:
            st.caption(ts)
            if dispatch_id:
                st.caption(f"Dispatch #{dispatch_id}")

        st.divider()

# ── Busca por artigo ──────────────────────────────────────────────────────────
st.markdown("### Histórico por Artigo")
article_id_input = st.text_input(
    "ID do artigo (cole o ID para ver histórico completo)",
    placeholder="ex: a1b2c3d4e5f6g7h8",
    key="audit_article_id",
)

if article_id_input.strip():
    try:
        art_history = article_audit_history(article_id_input.strip(), limit=50)
    except Exception as e:
        art_history = []
        st.error(f"Erro: {e}")

    if not art_history:
        st.info("Nenhuma ação encontrada para este artigo.")
    else:
        st.success(f"{len(art_history)} ação(ões) registrada(s) para este artigo.")
        df = pd.DataFrame(art_history)
        df["created_at"] = df["created_at"].apply(lambda v: fmt_dt(v, 16))
        cols_to_show = [c for c in ["created_at", "action", "actor", "from_status", "to_status", "notes"] if c in df.columns]
        st.dataframe(df[cols_to_show], use_container_width=True, hide_index=True)
