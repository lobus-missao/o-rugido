from __future__ import annotations

from datetime import date

import streamlit as st
from components import article_card

from o_rugido.repositories.articles import top_articles
from o_rugido.repositories.dashboard_queries import (
    editorial_counts_today,
    pending_approval_total,
)

st.set_page_config(page_title="Portal O Rugido", layout="wide")

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
st.caption("Pipeline editorial Piauí")

counts_today = editorial_counts_today()
pending_total = pending_approval_total()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Pendentes", pending_total, help="Artigos aguardando aprovação humana no Telegram")
m2.metric("Publicados hoje", counts_today.get("published", 0))
m3.metric("Rejeitados hoje", counts_today.get("rejected", 0))
m4.metric("Coletados hoje", counts_today.get("discovered", 0))

st.divider()

filt_col1, filt_col2 = st.columns(2)
with filt_col1:
    date_range = st.date_input(
        "Período",
        value=(date.today(), date.today()),
        format="DD/MM/YYYY",
        help="Filtra por data de publicação. Padrão: hoje.",
    )
with filt_col2:
    min_score = st.slider(
        "Score mínimo",
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
        "Nenhum artigo no período/score selecionado. "
        "Amplia o intervalo ou reduz o score mínimo. "
        "Coleta e ranqueio rodam automaticamente 3x/dia — se quiser forçar, vai em Operação."
    )
else:
    st.subheader(f"{len(articles)} artigos")
    for art in articles:
        article_card(art, show_actions=False, key_prefix="home")
