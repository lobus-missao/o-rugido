from __future__ import annotations

import streamlit as st
from components import article_card, run_cli, sidebar_controls

from news_radar.repositories.articles import top_articles

st.set_page_config(page_title="News Radar", layout="wide")

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

st.title("News Radar")
st.caption("Pipeline editorial Piaui")

col_a, col_b, _ = st.columns([1, 1, 4])
with col_a:
    if st.button("Coletar agora", use_container_width=True):
        result = run_cli("collect", "--limit-per-feed", "30", timeout=180)
        if result["ok"]:
            st.success(
                f"Coleta OK. {result.get('inserted', 0)} novos, "
                f"{result.get('updated', 0)} atualizados"
            )
        else:
            st.error(result.get("error", "falhou"))

with col_b:
    if st.button("Recalcular scores", use_container_width=True):
        result = run_cli("rank", timeout=120)
        if result["ok"]:
            st.success(result.get("output", "OK"))
        else:
            st.error(result.get("error"))

st.divider()

articles = top_articles(scope="piaui", limit=int(limit))

if not articles:
    st.info("Nenhum artigo. Rode `collect` + `rank`.")
else:
    st.subheader(f"{len(articles)} artigos")
    for art in articles:
        article_card(art, key_prefix="home")
