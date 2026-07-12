from __future__ import annotations

from datetime import date

import streamlit as st
from components import article_card, run_cli, sidebar_controls

from o_rugido.repositories.articles import top_articles

st.set_page_config(page_title="Portal O Rugido", layout="wide")

sidebar_controls()

with st.sidebar:
    st.markdown("### Listagem")
    limit = st.number_input(
        "Artigos a exibir",
        min_value=5,
        max_value=100,
        value=20,
        step=5,
        help="Quantos artigos mostrar na lista, ordenados por score.",
    )

st.title("Portal O Rugido")
st.caption("Pipeline editorial Piaui")

action_col1, action_col2 = st.columns(2)
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

filt_col1, filt_col2 = st.columns(2)
with filt_col1:
    date_range = st.date_input(
        "Periodo",
        value=(date.today(), date.today()),
        format="DD/MM/YYYY",
        help="Filtra por data de publicacao. Padrao: hoje.",
    )
with filt_col2:
    min_score = st.slider(
        "Score minimo",
        min_value=0, max_value=100, value=0, step=5,
        help="Mostra apenas artigos com score final acima desse valor.",
    )

if isinstance(date_range, tuple) and len(date_range) == 2:
    d_from, d_to = date_range
else:
    d_from = d_to = date_range if isinstance(date_range, date) else date.today()

articles = top_articles(
    scope="piaui",
    limit=int(limit),
    min_score=float(min_score) if min_score > 0 else None,
    date_from=d_from,
    date_to=d_to,
)

if not articles:
    st.info(
        "Nenhum artigo no periodo/score selecionado. "
        "Amplia o intervalo, reduz o score minimo ou roda `collect` + `rank`."
    )
else:
    st.subheader(f"{len(articles)} artigos")
    for art in articles:
        article_card(art, key_prefix="home")
