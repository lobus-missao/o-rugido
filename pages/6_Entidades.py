"""Aba Entidades — órgãos e pessoas mais citadas."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, PRIORITY_ICON
from news_radar.dashboard_queries import top_entities

st.set_page_config(page_title="Entidades · News Radar", page_icon="🏛️", layout="wide")
sidebar_controls()
st.title("🏛️ Entidades")
st.caption("Órgãos, pessoas e instituições mais citadas nas notícias analisadas pela IA.")

col1, col2 = st.columns(2)
with col1:
    hours = st.selectbox("Período", [6, 12, 24, 48, 168], index=2,
                         format_func=lambda h: f"Últimas {h}h" if h < 168 else "7 dias")
with col2:
    limit = st.slider("Top entidades", 10, 60, 30)

with st.spinner("Calculando entidades..."):
    try:
        entities = top_entities(hours=hours, limit=limit)
    except Exception as e:
        entities = []
        st.error(f"Erro: {e}")

if not entities:
    st.info("Nenhuma entidade encontrada. Processe lotes de IA para extrair entidades.")
    st.stop()

st.markdown(f"**{len(entities)} entidades** nas últimas {hours}h")

# ── Métricas rápidas ──────────────────────────────────────────────────────────
top3 = entities[:3]
if top3:
    c1, c2, c3 = st.columns(3)
    for col, ent in zip([c1, c2, c3], top3):
        col.metric(ent["name"].title()[:25],
                   f"{ent['count']} citações",
                   f"★ {ent['avg_score']:.1f} médio")

st.divider()

# ── Lista de entidades ────────────────────────────────────────────────────────
for ent in entities:
    prio = ent.get("top_priority") or ""
    icon = PRIORITY_ICON.get(prio, "⚪")
    srcs = ", ".join(ent["sources"][:3])
    with st.expander(
        f"{icon} **{ent['name'].title()[:40]}** — {ent['count']} citações · ★{ent['avg_score']:.1f} médio"
    ):
        col_a, col_b = st.columns([2, 1])
        with col_a:
            st.markdown("**Últimas notícias relacionadas:**")
            for art in ent.get("articles", []):
                score = art.get("score", 0)
                title = art.get("title", "")
                st.markdown(f"- {title[:70]} · ★{score:.0f}")
        with col_b:
            st.metric("Citações", ent["count"])
            st.metric("Score máximo", f"{ent['max_score']:.1f}")
            st.metric("Score médio", f"{ent['avg_score']:.1f}")
            st.markdown(f"**Prioridade:** {icon} {prio.upper() if prio else '-'}")
            if srcs:
                st.markdown(f"**Fontes:** {srcs}")
