"""
News Radar RSS — Dashboard principal (Radar).
Ponto de entrada do Streamlit multipage.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, article_card, fmt_dt, PRIORITY_COLOR, PRIORITY_ICON
from news_radar.dashboard_queries import radar_articles, ai_coverage_stats, compute_alerts

st.set_page_config(page_title="News Radar", page_icon="📡", layout="wide")
sidebar_controls()

st.title("📡 News Radar RSS")
st.caption("Central editorial de monitoramento — Piauí e Teresina")

# ── Métricas rápidas ──────────────────────────────────────────────────────────
try:
    cov = ai_coverage_stats()
    alerts = compute_alerts()
    n_criticos = sum(1 for a in alerts if a["severity"] == "critica")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📰 Artigos", cov["total"])
    c2.metric("🤖 Com IA", cov["with_ai"], f"{cov['pct_total']}%")
    c3.metric("🔴 Sem IA · score alto", cov["high_no_ai"])
    c4.metric("📦 Lotes pendentes", cov["batches"].get("pending", {}).get("count", 0))
    c5.metric("🚨 Alertas ativos", len(alerts),
              delta=f"{n_criticos} críticos" if n_criticos else None,
              delta_color="inverse")
except Exception as e:
    st.error(f"Erro ao carregar métricas: {e}")

st.divider()

# ── Filtros ───────────────────────────────────────────────────────────────────
col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns([2, 2, 2, 2, 3])
with col_f1:
    periodo_opts = {"Últimas 2h": 2, "Últimas 6h": 6, "Últimas 24h": 24, "3 dias": 72, "7 dias": 168}
    periodo_label = st.selectbox("⏱ Período", list(periodo_opts.keys()), index=2)
    hours = periodo_opts[periodo_label]
with col_f2:
    scope = st.selectbox("🌎 Escopo", ["brasil", "piaui", "teresina"])
with col_f3:
    prioridades = st.multiselect("🎯 Prioridade",
        ["critica", "alta", "media", "baixa", "ruido"],
        default=["critica", "alta", "media"])
with col_f4:
    ai_filter_opts = {"Todos": None, "Com IA": True, "Sem IA": False}
    ai_filter = st.selectbox("🤖 IA", list(ai_filter_opts.keys()))
    with_ai = ai_filter_opts[ai_filter]
with col_f5:
    search = st.text_input("🔍 Buscar", placeholder="palavra-chave, entidade, fonte...")

# ── Artigos ───────────────────────────────────────────────────────────────────
try:
    articles = radar_articles(
        hours=hours, scope=scope, limit=60,
        priority=prioridades or None,
        with_ai=with_ai,
        search=search or None,
    )
except Exception as e:
    articles = []
    st.error(f"Erro ao carregar artigos: {e}")

if not articles:
    st.info("Nenhum artigo encontrado com os filtros aplicados. Rode a coleta ou ajuste os filtros.")
else:
    st.markdown(f"**{len(articles)} artigos** — {periodo_label} · {scope.capitalize()}")

    # Grupos por prioridade
    groups = {"critica": [], "alta": [], "media": [], "baixa": [], "ruido": [], "": []}
    for a in articles:
        p = a.get("priority") or ""
        groups.get(p, groups[""]).append(a)

    # Grupos por prioridade — usa subheader+container (expanders não podem ser aninhados)
    for prio in ["critica", "alta", "media", "baixa", "ruido", ""]:
        arts = groups[prio]
        if not arts:
            continue
        icon = PRIORITY_ICON.get(prio, "⚪")
        label = prio.upper() if prio else "SEM PRIORIDADE"
        st.markdown(f"#### {icon} {label} — {len(arts)} notícia(s)")
        for art in arts[:20]:
            article_card(art, scope=scope, show_actions=True, key_prefix=f"radar_{prio}")
