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

PRIORITY_LABEL = {
    "critica": "Critica",
    "alta":    "Alta",
    "media":   "Media",
    "baixa":   "Baixa",
    "ruido":   "Ruido",
}

EDITORIAL_LABELS = {
    "discovered":      "Descoberto",
    "selected":        "Selecionado",
    "card_generated":  "Card gerado",
    "approved":        "Aprovado",
    "ready_to_publish": "Pronto para publicar",
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
        return {"ok": False, "error": f"Timeout apos {timeout}s"}
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


def priority_pill(priority: str) -> str:
    """Pill discreta com cor da prioridade. Retorna HTML."""
    color = PRIORITY_COLOR.get(priority, "#6b7280")
    label = PRIORITY_LABEL.get(priority, (priority or "-").capitalize())
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
        f'background:{color}15;color:{color};font-size:11px;font-weight:600;'
        f'border:1px solid {color}30;">{label}</span>'
    )


def article_card(art: dict, show_actions: bool = True, key_prefix: str = "") -> None:
    from news_radar.repositories.dashboard_queries import update_editorial_status

    priority = art.get("priority") or ""
    score = float(art.get("final_score_piaui") or 0)
    title = art.get("title") or ""
    source = art.get("source") or ""
    pub = fmt_dt(art.get("published_at"), 16)
    url = art.get("canonical_url") or art.get("url") or ""
    art_id = art.get("id", "")
    key = f"{key_prefix}_{art_id[:8]}"

    with st.container(border=True):
        meta_html = (
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">'
            f'{priority_pill(priority)}'
            f'<span style="color:#64748b;font-size:12px;">{source}</span>'
            f'<span style="color:#94a3b8;font-size:12px;">{pub}</span>'
            f'<span style="margin-left:auto;color:#475569;font-size:12px;font-weight:600;">'
            f'Score {score:.0f}</span>'
            f'</div>'
        )
        st.markdown(meta_html, unsafe_allow_html=True)

        if url:
            st.markdown(f"**[{title[:140]}]({url})**")
        else:
            st.markdown(f"**{title[:140]}**")

        summary = (art.get("summary") or "")[:200]
        if summary:
            st.markdown(
                f'<div style="color:#475569;font-size:13px;margin-top:4px;">{summary}</div>',
                unsafe_allow_html=True,
            )

        if show_actions:
            st.write("")
            c1, c2, c3, _ = st.columns([1, 1, 1, 3])
            with c1:
                if st.button("Selecionar", key=f"sel_{key}", use_container_width=True):
                    update_editorial_status(art_id, "selected")
                    st.rerun()
            with c2:
                if st.button("Rejeitar", key=f"rej_{key}", use_container_width=True):
                    update_editorial_status(art_id, "rejected")
                    st.rerun()
            with c3:
                if st.button("Arquivar", key=f"arch_{key}", use_container_width=True):
                    update_editorial_status(art_id, "archived")
                    st.rerun()


def sidebar_controls() -> None:
    with st.sidebar:
        st.markdown("### Controles")
        if st.button("Atualizar", use_container_width=True):
            st.rerun()
