"""Aba Alertas — alertas inteligentes sem IA automática."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
from news_radar.dash_utils import sidebar_controls, fmt_dt
from news_radar.dashboard_queries import compute_alerts, update_editorial_status

st.set_page_config(page_title="Alertas · News Radar", page_icon="🚨", layout="wide")
sidebar_controls()
st.title("🚨 Alertas")

SEVERITY_COLOR = {
    "critica": "#dc2626",
    "alta":    "#ea580c",
    "media":   "#d97706",
    "baixa":   "#16a34a",
    "info":    "#3b82f6",
}
SEVERITY_ICON = {
    "critica": "🔴",
    "alta":    "🟠",
    "media":   "🟡",
    "baixa":   "🟢",
    "info":    "🔵",
}

try:
    alerts = compute_alerts()
except Exception as e:
    alerts = []
    st.error(f"Erro: {e}")

if not alerts:
    st.success("✅ Nenhum alerta ativo no momento.")
    st.stop()

# ── Resumo ────────────────────────────────────────────────────────────────────
by_sev = {}
for a in alerts:
    s = a.get("severity", "info")
    by_sev[s] = by_sev.get(s, 0) + 1

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("🔴 Críticos",  by_sev.get("critica", 0))
c2.metric("🟠 Altos",     by_sev.get("alta", 0))
c3.metric("🟡 Médios",    by_sev.get("media", 0))
c4.metric("🟢 Baixos",    by_sev.get("baixa", 0))
c5.metric("🔵 Info",      by_sev.get("info", 0))

st.divider()

# ── Filtro ────────────────────────────────────────────────────────────────────
sev_filter = st.multiselect("Severidade",
    ["critica", "alta", "media", "baixa", "info"],
    default=["critica", "alta", "media"])

filtered = [a for a in alerts if a.get("severity") in (sev_filter or list(SEVERITY_ICON.keys()))]
st.markdown(f"**{len(filtered)} alertas**")

# ── Lista de alertas ──────────────────────────────────────────────────────────
for alrt in filtered:
    sev = alrt.get("severity", "info")
    color = SEVERITY_COLOR.get(sev, "#6b7280")
    icon = SEVERITY_ICON.get(sev, "🔵")
    time_str = fmt_dt(alrt.get("time"), 16)

    st.markdown(
        f'<div style="border-left:4px solid {color};padding:8px 12px;margin:6px 0;'
        f'background:#fafafa;border-radius:0 6px 6px 0;">'
        f'<span style="color:{color};font-weight:700;">{icon} {sev.upper()}</span>'
        f'<span style="color:#94a3b8;font-size:11px;margin-left:10px;">{time_str}</span><br>'
        f'<strong>{alrt.get("title","")}</strong><br>'
        f'<span style="color:#475569;font-size:13px;">{alrt.get("detail","")}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    col_act = st.columns(3)
    art_id = alrt.get("article_id")
    action = alrt.get("action", "")
    alert_type = alrt.get("type", "")

    with col_act[0]:
        if art_id and st.button("🎯 Selecionar", key=f"alrt_sel_{art_id[:8]}_{alert_type}"):
            update_editorial_status(art_id, "selected")
            st.rerun()

    with col_act[1]:
        if art_id:
            if st.button("🤖 Gerar prompt IA", key=f"alrt_prompt_{art_id[:8]}_{alert_type}"):
                st.session_state[f"alrt_prompt_{art_id}"] = True

    with col_act[2]:
        st.caption(f"💡 {action}")

    if art_id and st.session_state.get(f"alrt_prompt_{art_id}"):
        from news_radar.db import connect
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM articles WHERE id = %s", (art_id,))
                art_row = cur.fetchone()
        if art_row:
            art = dict(art_row)
            from news_radar.ai_batches import build_prompt, compact_article
            prompt = build_prompt("brasil", [compact_article(art)])
            st.text_area("Prompt para IA:", value=prompt, height=200,
                         key=f"alrt_prompt_area_{art_id[:8]}")
