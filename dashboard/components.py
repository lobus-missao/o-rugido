from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))


PRIORITY_COLOR = {
    "critica": "#dc2626",
    "alta":    "#ea580c",
    "media":   "#d97706",
    "baixa":   "#16a34a",
    "ruido":   "#6b7280",
}
PRIORITY_ICON = {
    "critica": "🔴",
    "alta":    "🟠",
    "media":   "🟡",
    "baixa":   "🟢",
    "ruido":   "⚫",
}
EDITORIAL_LABELS = {
    "discovered":      "Descoberto",
    "selected":        "Selecionado",
    "card_generated":  "Card gerado",
    "approved":        "Aprovado",
    "ready_to_publish":"Pronto para publicar",
    "rejected":        "Rejeitado",
    "published":       "Publicado",
    "archived":        "Arquivado",
}


PYTHON = sys.executable
CLI = [PYTHON, "-m", "news_radar.cli"]


def run_cli(*args, timeout: int = 120) -> dict:
    try:
        r = subprocess.run(
            CLI + list(args),
            capture_output=True, text=True, cwd=_ROOT, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout após {timeout}s"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}

    if r.returncode == 0:
        try:
            return {"ok": True, **json.loads(r.stdout)}
        except Exception:
            return {"ok": True, "output": r.stdout.strip()[:300]}

    raw_err = (r.stderr or r.stdout or "Erro desconhecido").strip()
    return {"ok": False, "error": raw_err[-400:] or raw_err[:200]}


def fmt_dt(value, chars: int = 16) -> str:
    if value is None:
        return ""
    return str(value)[:chars]


def priority_badge(priority: str) -> str:
    icon = PRIORITY_ICON.get(priority or "", "⚪")
    return f"{icon} {(priority or '-').upper()}"


def article_card(art: dict, show_actions: bool = True, key_prefix: str = "") -> None:
    from news_radar.repositories.dashboard_queries import update_editorial_status

    priority = art.get("priority") or ""
    color = PRIORITY_COLOR.get(priority, "#6b7280")
    score = float(art.get("final_score_piaui") or 0)
    title = art.get("title") or ""
    source = art.get("source") or ""
    pub = fmt_dt(art.get("published_at"), 16)
    url = art.get("canonical_url") or art.get("url") or ""
    art_id = art.get("id", "")
    key = f"{key_prefix}_{art_id[:8]}"

    with st.container():
        st.markdown(
            f'<div style="border-left:4px solid {color};padding:4px 10px;margin-bottom:6px;">'
            f'<span style="color:{color};font-weight:700;font-size:11px;">'
            f'{priority_badge(priority)}</span>'
            f'<span style="color:#94a3b8;font-size:11px;margin-left:12px;">'
            f'{source} · {pub}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        col_txt, col_score = st.columns([4, 1])
        with col_txt:
            if url:
                st.markdown(f"**[{title[:120]}]({url})**")
            else:
                st.markdown(f"**{title[:120]}**")
            summary = (art.get("summary") or "")[:160]
            if summary:
                st.caption(summary)

        with col_score:
            st.metric("Score", f"{score:.0f}")

        if show_actions:
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("🎯 Selecionar", key=f"sel_{key}"):
                    update_editorial_status(art_id, "selected")
                    st.rerun()
            with c2:
                if st.button("❌ Rejeitar", key=f"rej_{key}"):
                    update_editorial_status(art_id, "rejected")
                    st.rerun()
            with c3:
                if st.button("📦 Arquivar", key=f"arch_{key}"):
                    update_editorial_status(art_id, "archived")
                    st.rerun()

        st.divider()


def sidebar_controls() -> None:
    with st.sidebar:
        st.markdown("### Controles")
        if st.button("🔄 Atualizar"):
            st.rerun()
