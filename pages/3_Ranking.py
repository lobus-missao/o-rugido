"""Aba Ranking — com explicabilidade do score."""
from __future__ import annotations
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, fmt_dt, PRIORITY_COLOR, PRIORITY_ICON, run_cli
from news_radar.repository import top_articles
from news_radar.score_explainer import explain_score, COMPONENT_LABELS
from news_radar.dashboard_queries import opportunity_score, update_editorial_status

st.set_page_config(page_title="Ranking · News Radar", page_icon="📊", layout="wide")
sidebar_controls()
st.title("📊 Ranking")

# ── Filtros ───────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns([2, 1, 2, 2])
with col1:
    scope = st.radio("Escopo", ["brasil", "piaui", "teresina"], horizontal=True)
with col2:
    limit = st.slider("Top", 10, 200, 50)
with col3:
    dias_opts = {"Hoje (24h)": 1, "48h": 2, "7 dias": 7, "30 dias": 30, "Todos": None}
    dias_label = st.selectbox("Período", list(dias_opts.keys()), index=2)
    days_back = dias_opts[dias_label]
with col4:
    prio_filter = st.multiselect("Prioridade",
        ["critica", "alta", "media", "baixa", "ruido"],
        default=["critica", "alta", "media"])

col_s, col_p = st.columns([2, 2])
with col_s:
    search = st.text_input("🔍 Buscar", placeholder="título, resumo...")
with col_p:
    show_explanation = st.toggle("Mostrar explicação do score", value=False)

# ── Artigos ───────────────────────────────────────────────────────────────────
try:
    articles = top_articles(
        scope=scope, limit=limit, only_with_score=False,
        days_back=days_back, search=search or None,
        priority=prio_filter or None,
    )
except Exception as e:
    articles = []
    st.error(f"Erro: {e}")

score_col = f"final_score_{scope}"
st.markdown(f"**{len(articles)} artigos**")

for art in articles:
    priority = art.get("priority") or "-"
    score = float(art.get(score_col) or 0)
    auto_col = f"auto_score_{scope}"
    auto = float(art.get(auto_col) or 0)
    has_ai = bool(art.get("ai_score"))
    icon = PRIORITY_ICON.get(priority, "⚪")
    color = PRIORITY_COLOR.get(priority, "#6b7280")
    ai_badge = "🤖" if has_ai else "📊"
    pub = fmt_dt(art.get("published_at"), 13)
    url = art.get("canonical_url") or art.get("url") or ""

    ai_json = art.get("ai_json") or {}
    if isinstance(ai_json, str):
        try: ai_json = json.loads(ai_json)
        except: ai_json = {}

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
                pontos = ai_json.get("pontos_chave") or []
                for p in pontos[:4]:
                    st.markdown(f"- {p}")
                justif = ai_json.get("justificativa_score") or ""
                if justif:
                    st.caption(f"*{justif[:150]}*")

            if show_explanation:
                st.markdown("---")
                exp = explain_score(art, scope)
                st.markdown(f"💡 **{exp['explanation']}**")

                # Barras de componente
                comps = exp["components"]
                for key, data in comps.items():
                    label_info = COMPONENT_LABELS.get(key, (key, ""))
                    label_name = label_info[0]
                    val = data["value"]
                    mx = data["max"]
                    cnt = data.get("count")
                    pct = int(val / mx * 100) if mx else 0
                    cnt_str = f" ({cnt}×)" if cnt else ""
                    bar = f'<div style="background:#e2e8f0;border-radius:3px;height:5px;margin:2px 0"><div style="background:#3b82f6;width:{pct}%;height:5px;border-radius:3px;"></div></div>'
                    st.markdown(
                        f'<small>{label_name}{cnt_str}: **{val:.1f}**/{mx}</small>{bar}',
                        unsafe_allow_html=True,
                    )
                if exp["money_values_found"]:
                    st.caption(f"💲 {', '.join(exp['money_values_found'])}")

        with col_b:
            st.metric("Score final", f"{score:.1f}")
            st.metric("Score auto", f"{auto:.1f}")
            if has_ai:
                st.metric("Score IA", f"{float(art.get('ai_score') or 0):.1f}")
            st.metric("Oportunidade", f"{opp:.0f}",
                      help=opp_exp)
            st.caption(f"Card: {art.get('card_status','none')}")

            art_id = art.get("id", "")
            if st.button("🎯 Selecionar", key=f"rank_sel_{art_id[:8]}"):
                update_editorial_status(art_id, "selected")
                st.rerun()
            if not has_ai:
                if st.button("🤖 Gerar prompt IA", key=f"rank_prompt_{art_id[:8]}"):
                    st.session_state[f"show_prompt_{art_id}"] = True

        if st.session_state.get(f"show_prompt_{art_id}"):
            from news_radar.ai_batches import build_prompt, compact_article
            prompt = build_prompt(scope, [compact_article(art)])
            st.text_area("Prompt para IA:", value=prompt, height=200,
                         key=f"prompt_single_{art_id[:8]}")
