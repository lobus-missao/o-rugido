from __future__ import annotations

import pandas as pd
import streamlit as st
from components import run_cli

from o_rugido.repositories.dashboard_queries import daily_article_activity

st.set_page_config(page_title="Operação", layout="wide")

st.title("Operação")
st.caption("Ações manuais e produtividade editorial")

action_col1, action_col2, _ = st.columns([1, 1, 2])
with action_col1:
    if st.button("Coletar", use_container_width=True):
        result = run_cli("collect", "--limit-per-feed", "30", timeout=180)
        if result["ok"]:
            st.success(
                f"Coleta OK. {result.get('inserted', 0)} novos, "
                f"{result.get('updated', 0)} atualizados"
            )
        else:
            st.error(result.get("error", "falhou"))
with action_col2:
    if st.button("Recalcular", use_container_width=True):
        result = run_cli("rank", timeout=120)
        if result["ok"]:
            st.success(result.get("output", "OK"))
        else:
            st.error(result.get("error"))

st.divider()

st.subheader("Atividade diária (últimos 14 dias)")
activity = daily_article_activity(days=14)
if activity:
    df = pd.DataFrame(activity)
    df["count"] = df["count"].astype(int)
    st.bar_chart(df.set_index("date")["count"], height=220)
else:
    st.info("Sem dados de atividade no período.")

st.caption(
    "Métricas técnicas (saúde da API, banco, containers, workflows do n8n) "
    "estão na aba **Monitoramento**."
)
