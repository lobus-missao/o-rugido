"""Aba Operação — saúde do pipeline."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, run_cli, fmt_dt, load_feeds, save_feeds
from news_radar.dashboard_queries import pipeline_health
from news_radar.db import connect
import feedparser

st.set_page_config(page_title="Operação · News Radar", page_icon="⚙️", layout="wide")
sidebar_controls()
st.title("⚙️ Operação")

# ── Saúde do pipeline ─────────────────────────────────────────────────────────
try:
    health = pipeline_health()
    lc = health["last_collect"]
    w = health["articles_by_window"]
    cs = health["card_stats"]

    st.subheader("Pipeline")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📰 Total artigos", health["total_articles"])
    c2.metric("🕐 Últimas 2h", w.get("2h", 0))
    c3.metric("🕕 Últimas 6h", w.get("6h", 0))
    c4.metric("📅 Últimas 24h", w.get("24h", 0))
    c5.metric("⚠️ Feeds c/ erro (24h)", health["feeds_with_error_24h"])

    st.subheader("Cards")
    cc1, cc2, cc3, cc4 = st.columns(4)
    cc1.metric("🖼️ Total cards", cs.get("total_cards", 0))
    cc2.metric("✅ Aprovados", cs.get("approved", 0))
    cc3.metric("❌ Rejeitados", cs.get("rejected", 0))
    cc4.metric("⏳ Aguardando Telegram", cs.get("pending_tg", 0))

    if lc.get("last"):
        st.caption(f"Última coleta: {fmt_dt(lc['last'])} · {lc.get('total_collected', 0)} artigos · {lc.get('errors', 0)} erros de feed")
except Exception as e:
    st.error(f"Erro: {e}")

st.divider()

# ── Ações do pipeline ─────────────────────────────────────────────────────────
st.subheader("Ações")
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("▶ Coletar feeds", use_container_width=True):
        with st.spinner("Coletando 57 feeds... (pode levar ~2min)"):
            r = run_cli("collect", "--limit-per-feed", "30", timeout=180)
        if r["ok"]:
            st.success(f"✅ {r.get('inserted',0)} inseridos · {r.get('updated',0)} atualizados")
        else:
            st.error(r.get("error", "Erro"))

with col2:
    if st.button("▶ Recalcular ranking", use_container_width=True):
        with st.spinner("Ranqueando..."):
            r = run_cli("rank", timeout=90)
        st.success(r.get("output", "OK")) if r["ok"] else st.error(r.get("error"))

with col3:
    scope_op = st.selectbox("Escopo", ["brasil", "piaui", "teresina"], key="scope_op")
    if st.button("▶ Gerar lotes IA", use_container_width=True):
        with st.spinner("Gerando lotes..."):
            r = run_cli("make-ai-batches", "--scope", scope_op, "--top", "200",
                        "--batch-size", "30", "--days-back", "3")
        st.success(r.get("output", "OK")) if r["ok"] else st.error(r.get("error"))

with col4:
    if st.button("🗑️ Limpeza", use_container_width=True):
        r = run_cli("cleanup", "--days", "30", "--expire-batches-hours", "48")
        if r["ok"]:
            st.success(f"✅ {r.get('deleted_articles',0)} artigos removidos")

st.divider()

# ── Log de coletas ────────────────────────────────────────────────────────────
st.subheader("Log de coletas recentes")
try:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT source, status, collected_count, error, finished_at
                FROM feed_runs ORDER BY id DESC LIMIT 100
            """)
            runs = [dict(r) for r in cur.fetchall()]

    import pandas as pd
    if runs:
        df = pd.DataFrame(runs)
        df["finished_at"] = df["finished_at"].apply(lambda v: fmt_dt(v, 16))
        status_filter = st.multiselect("Status", ["ok", "warning", "error"],
                                       default=["ok", "warning", "error"], key="op_status")
        if status_filter:
            df = df[df["status"].isin(status_filter)]
        st.dataframe(df, use_container_width=True, height=350)
except Exception as e:
    st.error(f"Erro: {e}")
