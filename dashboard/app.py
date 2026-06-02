from __future__ import annotations

import streamlit as st
from components import article_card, run_cli, sidebar_controls

from news_radar.repositories.articles import top_articles

st.set_page_config(page_title="News Radar", layout="wide")

sidebar_controls()

st.title("News Radar")
st.caption("Pipeline editorial Piauí")

col_a, col_b, col_c = st.columns(3)
with col_a:
    if st.button("📥 Coletar agora"):
        result = run_cli("collect", "--limit-per-feed", "30", timeout=180)
        if result["ok"]:
            st.success(f"Coleta OK · {result.get('inserted', 0)} novos · {result.get('updated', 0)} atualizados")
        else:
            st.error(result.get("error", "falhou"))

with col_b:
    if st.button("🔢 Recalcular scores"):
        result = run_cli("rank", timeout=120)
        st.success(result.get("output", "OK")) if result["ok"] else st.error(result.get("error"))

with col_c:
    limit = st.number_input("Top N", min_value=5, max_value=100, value=20, step=5)

st.divider()

articles = top_articles(scope="piaui", limit=int(limit))

if not articles:
    st.info("Nenhum artigo. Rode `collect` + `rank`.")
else:
    st.subheader(f"Top {len(articles)} artigos · Piauí")
    for art in articles:
        article_card(art, key_prefix="home")
