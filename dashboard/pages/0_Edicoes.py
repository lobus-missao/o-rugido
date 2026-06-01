from __future__ import annotations

from datetime import date

import streamlit as st

from components import EDITORIAL_LABELS, fmt_dt, run_cli, sidebar_controls

from news_radar.repositories.dashboard_queries import dispatch_audit_history
from news_radar.services.editorial import (
    EDITIONS,
    approve_article,
    approve_card,
    get_edition_dispatches,
    reject_article,
    reject_card,
)

st.set_page_config(page_title="Edições", layout="wide")
sidebar_controls()

st.title("Edições")

col_date, col_edition, col_btn = st.columns([2, 2, 1])
with col_date:
    selected_date = st.date_input("Data", value=date.today())
with col_edition:
    edition = st.selectbox("Edição", list(EDITIONS.keys()))
with col_btn:
    if st.button("🚀 Criar dispatch"):
        result = run_cli("dispatch", "--edition", edition, "--top", "3")
        if result.get("ok"):
            st.success(f"{result.get('dispatched', 0)} dispatches criados")
        else:
            st.error(result.get("error", "falhou"))
        st.rerun()

st.divider()

dispatches = get_edition_dispatches(edition, selected_date)

if not dispatches:
    st.info(f"Nenhum dispatch em {selected_date} / {edition}.")
else:
    for d in dispatches:
        status = d.get("status", "")
        label = EDITORIAL_LABELS.get(status, status)
        dispatch_id = d.get("id")

        with st.expander(
            f"**#{d.get('rank')}** · {d.get('title', '')[:100]} · `{label}`",
            expanded=False,
        ):
            st.markdown(f"**Fonte:** {d.get('source', '')}")
            st.markdown(f"**Score Piauí:** {float(d.get('final_score_piaui') or 0):.0f}")
            url = d.get("canonical_url") or d.get("url") or ""
            if url:
                st.markdown(f"[Link original]({url})")
            summary = (d.get("summary") or "")[:300]
            if summary:
                st.caption(summary)

            st.divider()

            col1, col2, col3, col4 = st.columns(4)

            if status == "pending":
                with col1:
                    if st.button("✅ Aprovar notícia", key=f"apv_{dispatch_id}"):
                        approve_article(int(dispatch_id), "Dashboard", generate_card=True)
                        st.rerun()
                with col2:
                    if st.button("❌ Rejeitar", key=f"rej_{dispatch_id}"):
                        reject_article(int(dispatch_id), "Dashboard")
                        st.rerun()

            elif status == "card_generated":
                with col1:
                    if st.button("✅ Aprovar card", key=f"apvcd_{dispatch_id}"):
                        approve_card(int(dispatch_id), "Dashboard")
                        st.rerun()
                with col2:
                    if st.button("❌ Rejeitar card", key=f"rejcd_{dispatch_id}"):
                        reject_card(int(dispatch_id), "Dashboard")
                        st.rerun()

            card_path = d.get("card_path")
            if card_path:
                with col3:
                    st.caption(f"Card: `{card_path}`")

            with col4:
                if st.checkbox("Histórico", key=f"hist_{dispatch_id}"):
                    history = dispatch_audit_history(int(dispatch_id))
                    if not history:
                        st.caption("(sem ações)")
                    for h in history:
                        st.markdown(
                            f"- `{fmt_dt(h.get('created_at'), 16)}` "
                            f"**{h.get('action')}** por {h.get('actor', 'system')}"
                            f"{' · ' + (h.get('notes') or '') if h.get('notes') else ''}"
                        )
