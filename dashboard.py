"""
News Radar RSS — Dashboard principal.
Combina Radar (recentes) e Ranking (score) em abas unificadas.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st
from news_radar.dash_utils import (
    sidebar_controls, article_card, fmt_dt,
    PRIORITY_COLOR, PRIORITY_ICON, run_cli,
)
from news_radar.dashboard_queries import (
    radar_articles, ai_coverage_stats, compute_alerts,
    opportunity_score, update_editorial_status,
)
from news_radar.repository import top_articles
from news_radar.score_explainer import explain_score, COMPONENT_LABELS
from news_radar.ranking import RANKING_DIMENSIONS, score_summary, DIMENSION_ICONS
from news_radar.auto_classifier import classify_article, enrich_article_without_ai


def _build_instagram_prompt(art: dict, ai_json: dict) -> str:
    titulo = art.get("title", "").strip()
    resumo = ai_json.get("resumo_curto") or (art.get("summary") or "")[:200]
    pontos = ai_json.get("pontos_chave") or []
    categoria = art.get("category") or ai_json.get("editoria") or ""
    localidade = art.get("locality") or ai_json.get("localidade") or "Piauí"
    subtitulo = ai_json.get("subtitulo_sugerido") or ""
    titulo_sug = ai_json.get("titulo_sugerido") or titulo
    pontos_txt = "\n".join(f"• {p}" for p in pontos[:3]) if pontos else ""
    entidades = ai_json.get("entidades") or []
    prio = art.get("priority") or ""
    editoria = ai_json.get("editoria") or categoria or ""
    negativos = {"Segurança", "Justiça e controle", "Contas públicas", "Governos e política"}
    sugerir_caricatura = bool(entidades) and prio in ("critica", "alta") and editoria in negativos
    caricatura_bloco = ""
    if sugerir_caricatura:
        pessoa_principal = entidades[0]
        caricatura_bloco = f"""
ELEMENTO OPCIONAL — CARICATURA EDITORIAL:
Crie uma caricatura satírica de {pessoa_principal}.
- Traço editorial jornalístico (New Yorker / Revista Piauí)
- Exagere feições marcantes: expressão tensa, nervosa ou defensiva
- Tom crítico mas não ofensivo — humor inteligente
- Posicionar no terço superior da imagem, à esquerda
- Balão de fala opcional com frase irônica curta sobre o fato
SE PREFERIR: use ícone institucional abstrato no lugar da caricatura.
"""
    return f"""Crie uma imagem para post no Instagram no padrão visual do Partido Missão.

IDENTIDADE VISUAL:
- Cores: azul royal (#0033A0) e amarelo ouro (#FFD700)
- Fundo: azul escuro (#001A5C)
- Tipografia: bold, sem serifa, letras grandes
- Logotipo "PARTIDO MISSÃO" sempre visível
- Faixa em amarelo com texto em azul, ou vice-versa

CONTEÚDO:
Título: {titulo_sug}
{f'Subtítulo: {subtitulo}' if subtitulo else ''}
{f'Resumo: {resumo}' if resumo else ''}
{f'Editoria: {categoria}' if categoria else ''}
{f'Local: {localidade}' if localidade else ''}
{f'Envolvidos: {", ".join(entidades[:3])}' if entidades else ''}
{f'Pontos:{chr(10)}{pontos_txt}' if pontos_txt else ''}
{caricatura_bloco}
INSTRUÇÕES:
1. 1080×1080 px (feed) ou 1080×1920 px (stories)
2. Título em MAIÚSCULAS, bold, cor branca ou amarela, centralizado
3. Faixa amarela com destaque em azul
4. {'Caricatura ou ícone' if sugerir_caricatura else 'Ícone representativo'} no terço superior
5. Rodapé: "PARTIDO MISSÃO" + arroba
6. Máximo 3 elementos além de texto e logo

TEXTO PARA A IMAGEM:
"{titulo_sug.upper()}"
{f'"{subtitulo}"' if subtitulo else ''}

Chamada: "Saiba mais → [link na bio]"
""".strip()


st.set_page_config(page_title="News Radar", page_icon="📡", layout="wide")
sidebar_controls()

st.title("📡 News Radar RSS")
st.caption("Central editorial de monitoramento — Piauí e Teresina")

# ── Métricas rápidas ──────────────────────────────────────────────────────────
try:
    cov = ai_coverage_stats()
    alerts = compute_alerts()
    n_criticos = sum(1 for a in alerts if a["severity"] == "critica")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("📰 Artigos", cov["total"])
    c2.metric("🤖 Com IA", cov["with_ai"], f"{cov['pct_total']}%")
    c3.metric("🔴 Sem IA · score alto", cov["high_no_ai"])
    c4.metric("📦 Lotes pendentes", cov["batches"].get("pending", {}).get("count", 0))
    c5.metric("🚨 Alertas ativos", len(alerts),
              delta=f"{n_criticos} críticos" if n_criticos else None,
              delta_color="inverse")
except Exception as e:
    st.error(f"Erro ao carregar métricas: {e}")

st.divider()

# ── Filtros compartilhados ────────────────────────────────────────────────────
cf1, cf2, cf3, cf4 = st.columns([2, 2, 3, 3])
with cf1:
    scope = st.selectbox("🌎 Escopo", ["brasil", "piaui", "teresina"], key="main_scope")
with cf2:
    prioridades = st.multiselect(
        "🎯 Prioridade",
        ["critica", "alta", "media", "baixa", "ruido"],
        default=["critica", "alta", "media"],
        key="main_prio",
    )
with cf3:
    search = st.text_input("🔍 Buscar", placeholder="palavra-chave, entidade, fonte...", key="main_search")
with cf4:
    ai_filter_opts = {"Todos": None, "Com IA": True, "Sem IA": False}
    ai_filter = st.selectbox("🤖 IA", list(ai_filter_opts.keys()), key="main_ai")
    with_ai = ai_filter_opts[ai_filter]

# ── Abas ──────────────────────────────────────────────────────────────────────
tab_radar, tab_rank = st.tabs(["📰 Recentes", "📊 Ranking por score"])


# ════════════════════════════════════════════════════════════════════════════════
# ABA 1 — RECENTES
# ════════════════════════════════════════════════════════════════════════════════
with tab_radar:
    periodo_opts = {
        "Últimas 2h": 2, "Últimas 6h": 6, "Últimas 24h": 24,
        "3 dias": 72, "7 dias": 168,
    }
    periodo_label = st.selectbox(
        "⏱ Período", list(periodo_opts.keys()), index=2, key="radar_periodo"
    )
    hours = periodo_opts[periodo_label]

    try:
        articles = radar_articles(
            hours=hours, scope=scope, limit=60,
            priority=prioridades or None,
            with_ai=with_ai,
            search=search or None,
        )
    except Exception as e:
        articles = []
        st.error(f"Erro ao carregar artigos: {e}")

    if not articles:
        st.info("Nenhum artigo encontrado. Rode a coleta ou ajuste os filtros.")
    else:
        use_auto_classify = st.toggle(
            "🤖 Classificar sem IA (estimativa local)",
            value=True,
            key="radar_auto_classify",
            help="Aplica classificador Python para artigos sem IA real. "
                 "Preenche prioridade e editoria estimadas.",
        )

        if use_auto_classify:
            articles = [enrich_article_without_ai(a) for a in articles]

        st.markdown(f"**{len(articles)} artigos** — {periodo_label} · {scope.capitalize()}")

        groups: dict[str, list] = {
            "critica": [], "alta": [], "media": [], "baixa": [], "ruido": [], "": []
        }
        for a in articles:
            p = a.get("priority") or ""
            groups.get(p, groups[""]).append(a)

        for prio in ["critica", "alta", "media", "baixa", "ruido", ""]:
            arts = groups[prio]
            if not arts:
                continue
            icon = PRIORITY_ICON.get(prio, "⚪")
            label = prio.upper() if prio else "SEM PRIORIDADE"
            st.markdown(f"#### {icon} {label} — {len(arts)} notícia(s)")
            for art in arts[:20]:
                article_card(art, scope=scope, show_actions=True,
                             key_prefix=f"radar_{prio}")


# ════════════════════════════════════════════════════════════════════════════════
# ABA 2 — RANKING POR SCORE
# ════════════════════════════════════════════════════════════════════════════════
with tab_rank:
    rc1, rc2, rc3 = st.columns([1, 2, 2])
    with rc1:
        limit = st.slider("Top", 10, 200, 50, key="rank_limit")
    with rc2:
        dias_opts = {"Hoje (24h)": 1, "48h": 2, "7 dias": 7, "30 dias": 30, "Todos": None}
        dias_label = st.selectbox("Período", list(dias_opts.keys()), index=2, key="rank_dias")
        days_back = dias_opts[dias_label]
    with rc3:
        sort_dim = st.selectbox(
            "Ordenar por",
            ["final_score", "interesse_publico", "risco_investigativo",
             "dinheiro_publico", "gravidade", "urgencia", "relevancia_local"],
            format_func=lambda d: RANKING_DIMENSIONS.get(d, d),
            key="rank_sort_dim",
        )

    show_explanation = st.toggle("Mostrar explicação do score", value=True, key="rank_explain")

    try:
        rank_articles = top_articles(
            scope=scope, limit=limit, only_with_score=False,
            days_back=days_back, search=search or None,
            priority=prioridades or None,
        )
    except Exception as e:
        rank_articles = []
        st.error(f"Erro: {e}")

    score_col = f"final_score_{scope}"

    if sort_dim != "final_score" and rank_articles:
        from news_radar.ranking import _extract_ai_dimension
        rank_articles = sorted(rank_articles, key=lambda a: -_extract_ai_dimension(a, sort_dim))
        st.caption(f"Ordenado por: {RANKING_DIMENSIONS.get(sort_dim, sort_dim)}")

    st.markdown(f"**{len(rank_articles)} artigos**")

    for art in rank_articles:
        priority = art.get("priority") or "-"
        score = float(art.get(score_col) or 0)
        auto_col = f"auto_score_{scope}"
        auto = float(art.get(auto_col) or 0)
        has_ai = bool(art.get("ai_score"))
        icon = PRIORITY_ICON.get(priority, "⚪")
        color = PRIORITY_COLOR.get(priority, "#6b7280")
        ai_badge = "🤖" if has_ai else "📊"
        url = art.get("canonical_url") or art.get("url") or ""

        ai_json = art.get("ai_json") or {}
        if isinstance(ai_json, str):
            try:
                ai_json = json.loads(ai_json)
            except Exception:
                ai_json = {}

        category = art.get("category") or ai_json.get("editoria") or "-"
        opp, opp_exp = opportunity_score(art)

        label = f"{ai_badge} {icon} [{priority.upper()}] {art.get('title','')[:80]} — ★{score:.0f}"
        with st.expander(label):
            col_a, col_b = st.columns([3, 1])

            with col_a:
                st.markdown(f"**Fonte:** {art.get('source','')} · **Editoria:** {category}")
                if url:
                    st.markdown(f"[🔗 Abrir notícia]({url})")
                locality = art.get("locality") or ai_json.get("localidade") or ""
                if locality:
                    st.markdown(f"📍 {locality}")

                if has_ai:
                    resumo = ai_json.get("resumo_curto") or ""
                    if resumo:
                        st.markdown(f"> {resumo}")
                    for p in (ai_json.get("pontos_chave") or [])[:4]:
                        st.markdown(f"- {p}")
                    justif = ai_json.get("justificativa_score") or ""
                    if justif:
                        st.caption(f"*{justif[:150]}*")

                if show_explanation:
                    st.markdown("---")
                    exp = explain_score(art, scope)
                    st.markdown(f"💡 **{exp['explanation']}**")
                    for key, data in exp["components"].items():
                        label_info = COMPONENT_LABELS.get(key, (key, ""))
                        val = data["value"]
                        mx = data["max"]
                        cnt = data.get("count")
                        pct = int(val / mx * 100) if mx else 0
                        cnt_str = f" ({cnt}×)" if cnt else ""
                        bar = (
                            f'<div style="background:#e2e8f0;border-radius:3px;height:5px;margin:2px 0">'
                            f'<div style="background:#3b82f6;width:{pct}%;height:5px;border-radius:3px;"></div></div>'
                        )
                        st.markdown(
                            f'<small>{label_info[0]}{cnt_str}: **{val:.1f}**/{mx}</small>{bar}',
                            unsafe_allow_html=True,
                        )
                    if exp["money_values_found"]:
                        st.caption(f"💲 {', '.join(exp['money_values_found'])}")

            with col_b:
                st.metric("Score final", f"{score:.1f}")
                st.metric("Score auto", f"{auto:.1f}")
                if has_ai:
                    st.metric("Score IA", f"{float(art.get('ai_score') or 0):.1f}")
                st.metric("Oportunidade", f"{opp:.0f}", help=opp_exp)
                st.caption(f"Card: {art.get('card_status','none')}")

                if has_ai:
                    summ = score_summary(art, scope)
                    if summ["top_dimensions"]:
                        st.markdown("**Top dimensões IA:**")
                        for dim, val in summ["top_dimensions"]:
                            dim_icon = DIMENSION_ICONS.get(dim, "")
                            st.caption(f"{dim_icon} {dim}: **{val:.0f}**/10")
                else:
                    auto_cl = classify_article(art)
                    g = auto_cl["auto_gravidade"]
                    r = auto_cl["auto_risco_investigativo"]
                    u = auto_cl["auto_urgencia"]
                    if g > 0 or r > 0:
                        st.markdown("**Est. local (sem IA):**")
                        if g > 0:
                            st.caption(f"⚠️ Gravidade: **{g:.0f}**/10")
                        if r > 0:
                            st.caption(f"🔍 Risco invest.: **{r:.0f}**/10")
                        if u > 0:
                            st.caption(f"⚡ Urgência: **{u:.0f}**/10")
                        st.caption(f"📁 {auto_cl['auto_editoria']}")

                art_id = art.get("id", "")
                if st.button("🎯 Selecionar", key=f"rank_sel_{art_id[:8]}"):
                    update_editorial_status(art_id, "selected")
                    st.rerun()
                if not has_ai:
                    if st.button("🤖 Gerar prompt IA", key=f"rank_prompt_{art_id[:8]}"):
                        st.session_state[f"show_prompt_{art_id}"] = True
                if st.button("📸 Prompt Instagram", key=f"rank_insta_{art_id[:8]}"):
                    st.session_state[f"show_insta_{art_id}"] = True

            if st.session_state.get(f"show_prompt_{art_id}"):
                from news_radar.ai_batches import build_prompt, compact_article
                prompt = build_prompt(scope, [compact_article(art)])
                st.text_area("Prompt para IA:", value=prompt, height=200,
                             key=f"prompt_single_{art_id[:8]}")

            if st.session_state.get(f"show_insta_{art_id}"):
                _insta_prompt = _build_instagram_prompt(art, ai_json)
                st.text_area("📸 Prompt · Post Instagram — Partido Missão",
                             value=_insta_prompt, height=320,
                             key=f"insta_prompt_{art_id[:8]}")


