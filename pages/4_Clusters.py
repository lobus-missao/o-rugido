"""Aba Clusters — agrupamento de notícias similares com ranking explicável."""
from __future__ import annotations
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, fmt_dt, PRIORITY_COLOR, PRIORITY_ICON, run_cli
from news_radar.dashboard_queries import compute_clusters
from news_radar.ai_batches import build_prompt, compact_article
from news_radar.ranking import (
    RANKING_DIMENSIONS, DIMENSION_ICONS,
    explain_cluster_score, rank_clusters_by_dimension,
)

st.set_page_config(page_title="Clusters · News Radar", page_icon="🔵", layout="wide")
sidebar_controls()
st.title("🔵 Clusters de Notícias")
st.caption("Agrupa notícias similares para identificar assuntos quentes e evitar duplicidade editorial.")

# ── Métricas de clusters no banco ─────────────────────────────────────────────
try:
    from news_radar.clusters import cluster_stats
    stats = cluster_stats()
    if stats["total"] > 0:
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("Clusters ativos", stats["active"])
        mc2.metric("Artigos agrupados", stats["articles_clustered"])
        mc3.metric("Por título", stats["by_type"].get("titulo_similar", 0))
        mc4.metric("Por entidade", stats["by_type"].get("entidade_comum", 0))
except Exception:
    pass

# ── Abas: banco vs em memória ──────────────────────────────────────────────────
tab_db, tab_mem = st.tabs(["📦 Clusters Persistidos (banco)", "⚡ Computar em Tempo Real"])

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 1 — Clusters do banco (story_clusters + cluster_articles)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_db:
    st.subheader("Clusters Persistidos")

    # Filtros
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        db_scope = st.selectbox("Escopo", ["todos", "brasil", "piaui", "teresina"], key="db_scope")
    with col_f2:
        db_type = st.multiselect(
            "Tipo",
            ["titulo_similar", "entidade_comum", "keyword_comum"],
            default=["titulo_similar", "entidade_comum", "keyword_comum"],
            key="db_type",
        )
    with col_f3:
        db_limit = st.number_input("Máx. clusters", 5, 100, 30, key="db_limit")
    with col_f4:
        dim_options = list(RANKING_DIMENSIONS.keys())
        dim_labels = list(RANKING_DIMENSIONS.values())
        db_dimension = st.selectbox(
            "Ordenar por",
            dim_options,
            index=0,
            format_func=lambda d: RANKING_DIMENSIONS.get(d, d),
            key="db_dimension",
        )

    col_run, col_info = st.columns([1, 3])
    with col_run:
        hours_cluster = st.selectbox("Janela para recalcular", [24, 48, 72, 120], index=2, key="db_hours")
        min_size_cluster = st.number_input("Mín. artigos", 2, 10, 2, key="db_min")
        if st.button("🔄 Recalcular clusters", type="primary", use_container_width=True):
            scope_arg = db_scope if db_scope != "todos" else "todos"
            with st.spinner("Calculando e salvando clusters..."):
                r = run_cli(
                    "cluster-articles",
                    "--hours", str(hours_cluster),
                    "--min-size", str(min_size_cluster),
                    "--scope", scope_arg,
                    timeout=120,
                )
            if r["ok"]:
                n = r.get("clusters_created", 0)
                a = r.get("articles_clustered", 0)
                st.success(f"✅ {n} clusters salvos · {a} artigos agrupados")
                st.rerun()
            else:
                st.error(r.get("error", "Erro ao calcular clusters"))

    with col_info:
        st.info(
            "Clique em **Recalcular clusters** para agrupar artigos similares e salvar no banco. "
            "O processo é idempotente e pode ser executado periodicamente. "
            "Para automatizar, use: `python -m news_radar.cli cluster-articles --hours 72`"
        )

    st.divider()

    # Carrega clusters do banco
    try:
        from news_radar.clusters import list_db_clusters, get_db_cluster_articles, set_primary_article, archive_cluster
        scope_filter = None if db_scope == "todos" else db_scope
        db_clusters = list_db_clusters(scope=scope_filter, status="active", limit=int(db_limit))
        if db_type:
            db_clusters = [c for c in db_clusters if c["cluster_type"] in db_type]

        # Para dimensões que requerem artigos, pré-carrega (só se dimensão != cluster_score)
        articles_by_cluster: dict = {}
        if db_dimension not in ("cluster_score", "source_count", "article_count") and db_clusters:
            for c in db_clusters:
                try:
                    articles_by_cluster[c["id"]] = get_db_cluster_articles(c["id"])
                except Exception:
                    articles_by_cluster[c["id"]] = []

        # Aplica ranking multi-dimensional
        if db_clusters:
            db_clusters = rank_clusters_by_dimension(db_clusters, articles_by_cluster, db_dimension)
    except Exception as e:
        db_clusters = []
        st.error(f"Erro ao carregar clusters: {e}")

    if not db_clusters:
        st.info(
            "Nenhum cluster encontrado no banco. "
            "Clique em **Recalcular clusters** acima para gerar os primeiros agrupamentos."
        )
    else:
        st.markdown(f"**{len(db_clusters)} clusters** encontrados")

        type_labels = {
            "titulo_similar": "🔤 Título similar",
            "entidade_comum": "🏛️ Entidade comum",
            "keyword_comum":  "🔑 Keyword",
        }

        show_explanation = st.toggle("Mostrar explicação de score por cluster", value=True, key="db_show_exp")

        for i, cluster in enumerate(db_clusters):
            score = float(cluster.get("cluster_score") or 0)
            art_count = cluster.get("article_count", 0)
            src_count = cluster.get("source_count", 0)
            cluster_type = cluster.get("cluster_type", "")
            type_lbl = type_labels.get(cluster_type, cluster_type)
            rank_val = cluster.get("rank_value", score)
            rank_dim_lbl = RANKING_DIMENSIONS.get(db_dimension, db_dimension)

            header = (
                f"{type_lbl} **{cluster['title'][:55]}** "
                f"— {art_count} artigos · {src_count} fontes · "
                f"{rank_dim_lbl}: **{rank_val:.1f}**"
            )

            with st.expander(header, expanded=(i < 2)):
                col_meta, col_arts = st.columns([1, 2])

                with col_meta:
                    st.caption(f"ID: `{cluster['id']}`")
                    st.caption(f"Escopo: **{cluster['scope']}**")
                    st.caption(f"Tipo: {type_lbl}")
                    if cluster.get("label"):
                        st.caption(f"Label: _{cluster['label']}_")
                    st.caption(f"Score: **{score:.2f}**")
                    st.caption(f"Atualizado: {fmt_dt(cluster.get('updated_at'), 16)}")

                    # Explicação de score
                    if show_explanation:
                        arts_for_exp = articles_by_cluster.get(cluster["id"])
                        if arts_for_exp is None:
                            try:
                                arts_for_exp = get_db_cluster_articles(cluster["id"])
                            except Exception:
                                arts_for_exp = []
                        exp = explain_cluster_score(cluster, arts_for_exp)
                        st.markdown(f"💡 _{exp['explanation']}_")
                        if exp["has_ai"] and exp["ai_dimensions"]:
                            st.caption(f"Análise de IA: {exp['ai_article_count']}/{art_count} artigos")
                            # Top dimensões IA com barra
                            top_dims = sorted(
                                exp["ai_dimensions"].items(), key=lambda x: -x[1]
                            )[:5]
                            for dim, val in top_dims:
                                icon = DIMENSION_ICONS.get(dim, "")
                                pct = int(val * 10)
                                bar = (
                                    f'<div style="background:#e2e8f0;border-radius:3px;height:4px;margin:1px 0">'
                                    f'<div style="background:#3b82f6;width:{pct}%;height:4px;border-radius:3px;"></div>'
                                    f'</div>'
                                )
                                st.markdown(
                                    f'<small>{icon} {dim}: **{val:.1f}**/10</small>{bar}',
                                    unsafe_allow_html=True,
                                )

                    st.divider()

                    # Ações
                    if st.button("🗄️ Arquivar cluster", key=f"arch_{cluster['id']}", type="secondary"):
                        try:
                            archive_cluster(cluster["id"])
                            st.success("Cluster arquivado.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro: {e}")

                with col_arts:
                    try:
                        arts = get_db_cluster_articles(cluster["id"])
                    except Exception as e:
                        arts = []
                        st.error(f"Erro ao carregar artigos: {e}")

                    if arts:
                        st.markdown(f"**{len(arts)} artigos:**")
                        for art in arts[:8]:
                            p = art.get("priority") or ""
                            s = float(art.get("final_score_brasil") or 0)
                            src = art.get("source") or ""
                            url = art.get("canonical_url") or ""
                            title = art.get("title") or ""
                            ai_ico = "🤖" if art.get("ai_score") else "📊"
                            prim = "⭐ " if art.get("is_primary") else ""

                            if url:
                                st.markdown(
                                    f"{prim}{ai_ico} {PRIORITY_ICON.get(p,'⚪')} "
                                    f"[{title[:65]}]({url}) · {src} · ★{s:.0f}"
                                )
                            else:
                                st.markdown(
                                    f"{prim}{ai_ico} {PRIORITY_ICON.get(p,'⚪')} "
                                    f"**{title[:65]}** · {src} · ★{s:.0f}"
                                )

                        # Selecionar artigo primário
                        art_options = {a["title"][:60]: a["id"] for a in arts}
                        current_primary = next(
                            (a["title"][:60] for a in arts if a.get("is_primary")), None
                        )
                        sel = st.selectbox(
                            "Definir primário:",
                            list(art_options.keys()),
                            index=list(art_options.keys()).index(current_primary)
                            if current_primary in art_options
                            else 0,
                            key=f"primary_{cluster['id']}",
                        )
                        if st.button("⭐ Definir como primário", key=f"set_prim_{cluster['id']}"):
                            try:
                                set_primary_article(cluster["id"], art_options[sel])
                                st.success(f"Artigo primário atualizado.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erro: {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ABA 2 — Clustering em tempo real (in-memory, comportamento anterior)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_mem:
    st.subheader("Clustering em Tempo Real")
    st.caption("Calcula agrupamentos diretamente dos artigos sem salvar no banco — útil para exploração.")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        hours = st.selectbox("Janela", [6, 12, 24, 48, 72], index=2,
                             format_func=lambda h: f"{h}h", key="mem_hours")
    with col_f2:
        min_size = st.number_input("Mínimo de artigos", 2, 10, 2, key="mem_min")
    with col_f3:
        show_type = st.multiselect(
            "Tipo de cluster",
            ["titulo_similar", "entidade_comum", "keyword_comum"],
            default=["titulo_similar", "entidade_comum", "keyword_comum"],
            key="mem_type",
        )

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
                "keyword_comum":  "🔑 Keyword",
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

                    if st.button("🤖 Gerar prompt IA", key=f"cluster_prompt_{i}"):
                        arts = cluster["articles"][:10]
                        compact = [compact_article(a) for a in arts]
                        prompt = build_prompt("brasil", compact)
                        st.session_state[f"cluster_prompt_text_{i}"] = prompt

                    if st.session_state.get(f"cluster_prompt_text_{i}"):
                        st.code(
                            st.session_state[f"cluster_prompt_text_{i}"],
                            language=None,
                        )

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
                            st.markdown(
                                f"{ai} {PRIORITY_ICON.get(p,'⚪')} [{title[:65]}]({url}) · {src} · ★{s:.0f}"
                            )
                        else:
                            st.markdown(
                                f"{ai} {PRIORITY_ICON.get(p,'⚪')} **{title[:65]}** · {src} · ★{s:.0f}"
                            )
