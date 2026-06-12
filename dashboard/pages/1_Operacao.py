from __future__ import annotations

import pandas as pd
import streamlit as st
from components import fmt_dt, sidebar_controls

from news_radar.repositories.dashboard_queries import (
    daily_article_activity,
    pipeline_health,
    recent_editorial_actions,
    sources_summary,
)

st.set_page_config(page_title="Operacao", layout="wide")
sidebar_controls()

st.title("Operacao")
st.caption("Saude do pipeline")

health = pipeline_health()
srcs = sources_summary()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Artigos", health["total_articles"])
col2.metric("Classificados", health["classified"])
col3.metric("Fontes ativas", f"{srcs['enabled']}/{srcs['total']}")
col4.metric("Erros 24h", health["errors_24h"])

last = health["last_collect_ok"]
if last:
    st.caption(f"Ultima coleta com sucesso: {fmt_dt(last, 19)}")
else:
    st.warning("Nenhuma coleta com sucesso registrada.")

st.divider()

st.subheader("Atividade diaria (ultimos 14 dias)")
activity = daily_article_activity(days=14)
if activity:
    df = pd.DataFrame(activity)
    df["count"] = df["count"].astype(int)
    st.bar_chart(df.set_index("date")["count"], height=220)
else:
    st.info("Sem dados de atividade no periodo.")

st.divider()

st.subheader("Ultimas acoes editoriais")
actions = recent_editorial_actions(limit=20)
if not actions:
    st.info("Nenhuma acao registrada.")
else:
    for a in actions:
        article_id = a.get("article_id") or ""
        article_suffix = f" (artigo {article_id[:8]})" if article_id else ""
        notes = a.get("notes")
        notes_suffix = f" — {notes}" if notes else ""
        st.markdown(
            f"- `{fmt_dt(a.get('created_at'), 16)}` "
            f"**{a.get('action')}** por {a.get('actor', 'system')}"
            f"{article_suffix}{notes_suffix}"
        )
