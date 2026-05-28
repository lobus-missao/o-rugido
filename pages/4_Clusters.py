"""Aba Clusters — agrupamento de notícias similares."""
from __future__ import annotations
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, fmt_dt, PRIORITY_COLOR, PRIORITY_ICON
from news_radar.dashboard_queries import compute_clusters
from news_radar.ai_batches import build_prompt, compact_article

st.set_page_config(page_title="Clusters · News Radar", page_icon="🔵", layout="wide")
sidebar_controls()
st.title("🔵 Clusters de Notícias")
st.caption("Agrupa notícias similares para evitar duplicidade editorial e identificar assuntos quentes.")

col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    hours = st.selectbox("Janela", [6, 12, 24, 48, 72], index=2, format_func=lambda h: f"{h}h")
with col_f2:
    min_size = st.number_input("Mínimo de artigos no cluster", 2, 10, 2)
with col_f3:
    show_type = st.multiselect("Tipo de cluster",
        ["titulo_similar", "entidade_comum", "keyword_comum"],
        default=["titulo_similar", "entidade_comum", "keyword_comum"])

with st.spinner("Calculando clusters..."):
    try:
        clusters = compute_clusters(hours=hours, min_size=min_size)
        if show_type:
            clusters = [c for c in clusters if c["type"] in show_type]
    except Exception as e:
        clusters = []
        st.error(f"Erro: {e}")

if not clusters:
    st.info("Nenhum cluster encontrado no período. Tente ampliar a janela de tempo.")
else:
    st.markdown(f"**{len(clusters)} clusters** encontrados nas últimas {hours}h")

    for i, cluster in enumerate(clusters):
        prio = cluster.get("top_priority") or ""
        color = PRIORITY_COLOR.get(prio, "#6b7280")
        icon = PRIORITY_ICON.get(prio, "⚪")
        has_ai = cluster.get("has_ai", False)
        type_labels = {
            "titulo_similar": "🔤 Título similar",
            "entidade_comum": "🏛️ Entidade comum",
            "keyword_comum": "🔑 Keyword",
        }
        type_label = type_labels.get(cluster["type"], cluster["type"])

        header = (
            f"{icon} **{cluster['label'][:60]}** "
            f"— {cluster['size']} artigos · ★{cluster['max_score']:.0f} max "
            f"· {'🤖 tem IA' if has_ai else '📊 sem IA'}"
        )

        with st.expander(header, expanded=i < 3):
            col_info, col_arts = st.columns([1, 2])

            with col_info:
                st.markdown(f"**Tipo:** {type_label}")
                st.markdown(f"**Prioridade:** {icon} {prio.upper() if prio else '-'}")
                st.markdown(f"**Score médio:** {cluster['avg_score']:.1f}")
                if cluster.get("locality"):
                    st.markdown(f"📍 {cluster['locality']}")
                if cluster.get("entities"):
                    st.markdown("**Entidades:**")
                    for ent in cluster["entities"]:
                        st.markdown(f"  - {ent}")
                if cluster.get("sources"):
                    st.markdown(f"**Fontes:** {', '.join(cluster['sources'][:4])}")
                if cluster.get("first_pub"):
                    st.caption(f"Primeiro: {fmt_dt(cluster['first_pub'], 16)}")
                if cluster.get("last_pub"):
                    st.caption(f"Último: {fmt_dt(cluster['last_pub'], 16)}")

                # Gerar prompt de IA para o cluster
                if st.button("🤖 Gerar prompt IA", key=f"cluster_prompt_{i}"):
                    arts = cluster["articles"][:10]
                    compact = [compact_article(a) for a in arts]
                    # Usa brasil como scope padrão
                    prompt = build_prompt("brasil", compact)
                    st.session_state[f"cluster_prompt_text_{i}"] = prompt

                if st.session_state.get(f"cluster_prompt_text_{i}"):
                    st.text_area("Prompt gerado:", value=st.session_state[f"cluster_prompt_text_{i}"],
                                 height=200, key=f"cluster_prompt_area_{i}")

            with col_arts:
                st.markdown(f"**{len(cluster['articles'])} artigos:**")
                for art in cluster["articles"][:8]:
                    p = art.get("priority") or ""
                    s = float(art.get("final_score_brasil") or 0)
                    src = art.get("source") or ""
                    url = art.get("canonical_url") or art.get("url") or ""
                    title = art.get("title") or ""
                    ai = "🤖" if art.get("ai_score") else "📊"
                    if url:
                        st.markdown(f"{ai} {PRIORITY_ICON.get(p,'⚪')} [{title[:65]}]({url}) · {src} · ★{s:.0f}")
                    else:
                        st.markdown(f"{ai} {PRIORITY_ICON.get(p,'⚪')} **{title[:65]}** · {src} · ★{s:.0f}")
