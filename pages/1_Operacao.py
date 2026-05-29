"""Aba Operação — saúde do pipeline."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, run_cli, fmt_dt, load_feeds, save_feeds
from news_radar.dashboard_queries import (
    pipeline_health, sources_summary, recent_editorial_actions, daily_article_activity
)
from news_radar.scheduler import _is_enabled as scheduler_is_enabled
from news_radar.dispatch import EDITIONS
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

# ── Fontes no Banco ───────────────────────────────────────────────────────────
try:
    src_stats = sources_summary()
    if src_stats["total"] > 0:
        st.subheader("Fontes (tabela sources)")
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("📦 Total no banco", src_stats["total"])
        sc2.metric("✅ Habilitadas", src_stats["enabled"])
        sc3.metric("❌ Com erro acumulado", src_stats["with_error"])
except Exception:
    pass

st.divider()

# ── Scheduler Interno ─────────────────────────────────────────────────────────
st.subheader("Scheduler Interno")
if scheduler_is_enabled():
    st.success("Scheduler ativo (NEWS_RADAR_SCHEDULER=1)")
    st.caption(
        "O scheduler interno está habilitado e assume coleta e dispatch automáticos. "
        "O n8n pode ser desativado com segurança — o guard de idempotência em "
        "create_dispatch() evita envios duplicados caso ambos rodem simultaneamente."
    )
    st.markdown("**Horários agendados:**")
    sched_cols = st.columns(4)
    sched_cols[0].metric("Coleta RSS", "a cada 30 min")
    for i, (edition, info) in enumerate(EDITIONS.items(), start=1):
        h = info["dispatch_hour"]
        m = info["dispatch_min"]
        sched_cols[i].metric(f"Dispatch {edition}", f"{h:02d}:{m:02d}")
else:
    st.info(
        "Scheduler interno desativado (NEWS_RADAR_SCHEDULER=0). "
        "O n8n é o scheduler atual. Para ativar o scheduler interno, "
        "defina NEWS_RADAR_SCHEDULER=1 no .env e reinicie a API."
    )

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
        if r["ok"]:
            st.success(str(r.get("output", "Ranking recalculado.")))
        else:
            st.error(str(r.get("error", "Erro desconhecido")))

with col3:
    scope_op = st.selectbox("Escopo", ["brasil", "piaui", "teresina"], key="scope_op")
    if st.button("▶ Gerar lotes IA", use_container_width=True):
        with st.spinner("Gerando lotes..."):
            r = run_cli("make-ai-batches", "--scope", scope_op, "--top", "200",
                        "--batch-size", "30", "--days-back", "3")
        if r["ok"]:
            st.success(str(r.get("output", "Lotes gerados.")))
        else:
            st.error(str(r.get("error", "Erro desconhecido")))

with col4:
    if st.button("🗑️ Limpeza", use_container_width=True):
        r = run_cli("cleanup", "--days", "30", "--expire-batches-hours", "48")
        if r["ok"]:
            st.success(f"✅ {r.get('deleted_articles',0)} artigos removidos")

st.divider()

# ── Atividade diária — Calendar heatmap ──────────────────────────────────────
st.subheader("📅 Atividade diária de captura")
try:
    import altair as alt
    import pandas as pd
    from datetime import datetime, timedelta

    days_option = st.select_slider(
        "Janela de tempo",
        options=[30, 60, 90, 180],
        value=90,
        key="heatmap_days",
        format_func=lambda d: f"{d} dias",
    )

    activity = daily_article_activity(days_back=days_option)

    if activity:
        df_act = pd.DataFrame(activity)
        df_act["date"] = pd.to_datetime(df_act["date"])

        # Preenche dias sem artigos com 0
        all_days = pd.date_range(
            end=datetime.today(),
            periods=days_option,
            freq="D",
        )
        df_full = (
            pd.DataFrame({"date": all_days})
            .merge(df_act, on="date", how="left")
            .fillna(0)
        )
        df_full["count"] = df_full["count"].astype(int)
        df_full["weekday"] = df_full["date"].dt.weekday      # 0=Seg … 6=Dom
        df_full["week_str"] = df_full["date"].dt.strftime("%Y-W%V")  # ISO week
        df_full["date_str"] = df_full["date"].dt.strftime("%d/%m/%Y")
        df_full["day_name"] = df_full["date"].dt.strftime("%a")

        # ── Heatmap estilo GitHub ─────────────────────────────────────────────
        heatmap = (
            alt.Chart(df_full)
            .mark_rect(cornerRadius=3)
            .encode(
                x=alt.X(
                    "week_str:O",
                    title=None,
                    axis=alt.Axis(
                        labels=False, ticks=False, grid=False, domain=False
                    ),
                ),
                y=alt.Y(
                    "weekday:O",
                    title=None,
                    sort=[0, 1, 2, 3, 4, 5, 6],
                    axis=alt.Axis(
                        labelExpr="['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'][datum.value]",
                        ticks=False,
                        grid=False,
                        domain=False,
                    ),
                ),
                color=alt.Color(
                    "count:Q",
                    scale=alt.Scale(
                        scheme="greens",
                        domain=[0, max(df_full["count"].max(), 1)],
                    ),
                    legend=alt.Legend(title="Artigos"),
                ),
                tooltip=[
                    alt.Tooltip("date_str:N", title="Data"),
                    alt.Tooltip("count:Q", title="Artigos"),
                    alt.Tooltip("brasil:Q", title="Brasil"),
                    alt.Tooltip("piaui:Q", title="Piauí"),
                    alt.Tooltip("teresina:Q", title="Teresina"),
                ],
            )
            .properties(height=140, title="Artigos capturados por dia")
        )
        st.altair_chart(heatmap, use_container_width=True)

        # ── Linha de tendência por escopo ─────────────────────────────────────
        scope_view = st.radio(
            "Breakdown",
            ["Total", "Por escopo"],
            horizontal=True,
            key="heatmap_scope",
        )

        if scope_view == "Por escopo":
            df_scope = df_full[["date", "brasil", "piaui", "teresina"]].copy()
            df_scope = df_scope.melt(id_vars="date", var_name="escopo", value_name="artigos")
            line = (
                alt.Chart(df_scope)
                .mark_area(opacity=0.6, interpolate="monotone")
                .encode(
                    x=alt.X("date:T", title="Data", axis=alt.Axis(format="%d/%m")),
                    y=alt.Y("artigos:Q", title="Artigos", stack=None),
                    color=alt.Color(
                        "escopo:N",
                        scale=alt.Scale(
                            domain=["brasil", "piaui", "teresina"],
                            range=["#3b82f6", "#10b981", "#f59e0b"],
                        ),
                    ),
                    tooltip=["date:T", "escopo:N", "artigos:Q"],
                )
                .properties(height=160)
            )
            st.altair_chart(line, use_container_width=True)
        else:
            line = (
                alt.Chart(df_full)
                .mark_area(
                    color="#3b82f6",
                    opacity=0.7,
                    interpolate="monotone",
                    line={"color": "#1d4ed8"},
                )
                .encode(
                    x=alt.X("date:T", title="Data", axis=alt.Axis(format="%d/%m")),
                    y=alt.Y("count:Q", title="Artigos capturados"),
                    tooltip=[
                        alt.Tooltip("date_str:N", title="Data"),
                        alt.Tooltip("count:Q", title="Total"),
                    ],
                )
                .properties(height=140)
            )
            st.altair_chart(line, use_container_width=True)

        # Resumo rápido
        col_s1, col_s2, col_s3 = st.columns(3)
        days_with_articles = int((df_full["count"] > 0).sum())
        col_s1.metric("Dias com captura", f"{days_with_articles}/{days_option}")
        col_s2.metric("Média diária", f"{df_full['count'].mean():.1f}")
        col_s3.metric("Pico", f"{int(df_full['count'].max())} artigos")
    else:
        st.info("Nenhum artigo registrado no período.")
except Exception as e:
    st.caption(f"Heatmap indisponível: {e}")

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

# ── Ações Editoriais Recentes ─────────────────────────────────────────────────
st.divider()
st.subheader("Ações Editoriais Recentes")
try:
    actions = recent_editorial_actions(limit=15)
    if actions:
        import pandas as pd
        df_actions = pd.DataFrame([
            {
                "Quando": fmt_dt(a.get("created_at"), 16),
                "Ação": a.get("action", ""),
                "Ator": a.get("actor", ""),
                "De": a.get("from_status") or "—",
                "Para": a.get("to_status") or "—",
                "Artigo": (a.get("article_title") or "")[:60] or "—",
                "Dispatch": a.get("dispatch_id") or "—",
            }
            for a in actions
        ])
        st.dataframe(df_actions, use_container_width=True, height=320)
    else:
        st.info(
            "Nenhuma ação editorial registrada ainda. "
            "Ações de aprovação/rejeição serão registradas automaticamente a partir de agora."
        )
except Exception as e:
    st.caption(f"Ações editoriais indisponíveis: {e}")
