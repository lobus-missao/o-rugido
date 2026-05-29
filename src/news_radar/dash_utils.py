"""Utilitários compartilhados entre todas as páginas do dashboard."""
from __future__ import annotations
import sys
from pathlib import Path

# Garante que o src está no path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

import json
import subprocess
from datetime import datetime

import streamlit as st
import yaml

from news_radar.config import FEEDS_PATH

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
    "needs_ai":        "Precisa de IA",
    "ai_done":         "IA pronta",
    "selected":        "Selecionado",
    "card_generated":  "Card gerado",
    "sent_to_telegram":"Enviado",
    "approved":        "Aprovado",
    "ready_to_publish":"Pronto para publicar",
    "rejected":        "Rejeitado",
    "published":       "Publicado",
    "archived":        "Arquivado",
}

PYTHON = sys.executable  # funciona em Windows (.venv) e Docker (sistema)
CLI = [PYTHON, "-m", "news_radar.cli"]


def run_cli(*args, timeout=120) -> dict:
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

    # Garante string limpa para evitar _repr_html_() no Streamlit
    raw_err = (r.stderr or r.stdout or "Erro desconhecido").strip()
    # Remove linhas de warning WSL e box-drawing do Playwright
    lines = [l for l in raw_err.splitlines()
             if not l.startswith("<3>WSL") and "UtilGetPpid" not in l]
    clean = "\n".join(lines).strip()[-400:] or raw_err[:200]
    return {"ok": False, "error": clean}


def fmt_dt(value, chars: int = 16) -> str:
    if value is None:
        return ""
    return str(value)[:chars]


def priority_badge(priority: str) -> str:
    icon = PRIORITY_ICON.get(priority or "", "⚪")
    return f"{icon} {(priority or '-').upper()}"


def score_bar(score: float, color: str = "#3b82f6") -> str:
    w = min(100, max(0, score))
    return f'<div style="background:#e2e8f0;border-radius:4px;height:6px;"><div style="background:{color};width:{w}%;height:6px;border-radius:4px;"></div></div>'


def article_card(art: dict, scope: str = "brasil", show_actions: bool = True, key_prefix: str = "") -> None:
    """Renderiza card compacto de artigo no Streamlit."""
    from news_radar.dashboard_queries import update_editorial_status, opportunity_score
    from news_radar.score_explainer import explain_score

    priority = art.get("priority") or ""
    color = PRIORITY_COLOR.get(priority, "#6b7280")
    score_col = f"final_score_{scope}"
    score = float(art.get(score_col) or 0)
    has_ai = bool(art.get("ai_score"))
    title = art.get("title") or ""
    source = art.get("source") or ""
    pub = fmt_dt(art.get("published_at"), 16)
    url = art.get("canonical_url") or art.get("url") or ""
    ed_status = art.get("editorial_status") or "discovered"

    ai_json = art.get("ai_json") or {}
    if isinstance(ai_json, str):
        try: ai_json = json.loads(ai_json)
        except: ai_json = {}

    locality = art.get("locality") or ai_json.get("localidade") or ""
    entities = ai_json.get("entidades") or []
    resumo = ai_json.get("resumo_curto") or (art.get("summary") or "")[:120]

    opp_score, opp_exp = opportunity_score(art)

    art_id = art.get("id", "")
    key = f"{key_prefix}_{art_id[:8]}"

    with st.container():
        # Header colorido
        st.markdown(
            f'<div style="border-left:4px solid {color};padding:4px 10px;margin-bottom:6px;">'
            f'<span style="color:{color};font-weight:700;font-size:11px;">'
            f'{priority_badge(priority)}</span>'
            f'<span style="color:#94a3b8;font-size:11px;margin-left:12px;">'
            f'{"🤖 IA" if has_ai else "📊 Auto"} · {source} · {pub}'
            f'{"  · 📍 " + locality if locality else ""}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        col_txt, col_score = st.columns([4, 1])
        with col_txt:
            if url:
                st.markdown(f"**[{title[:100]}]({url})**")
            else:
                st.markdown(f"**{title[:100]}**")
            if resumo:
                st.caption(resumo[:150])
            if entities:
                tags = " ".join([f"`{e}`" for e in entities[:4]])
                st.markdown(tags)

        with col_score:
            st.metric("Score", f"{score:.0f}")
            st.markdown(f"<small>Oport. **{opp_score:.0f}**</small>", unsafe_allow_html=True)

        if show_actions:
            with st.expander("Ações", expanded=False):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    if st.button("🎯 Selecionar", key=f"sel_{key}"):
                        update_editorial_status(art_id, "selected")
                        st.rerun()
                with c2:
                    if st.button("🖼️ Gerar card", key=f"card_{key}"):
                        r = run_cli("make-card", "--scope", scope, "--limit", "1", timeout=30)
                        st.success("Card gerado!") if r["ok"] else st.error(r.get("error"))
                with c3:
                    if st.button("❌ Rejeitar", key=f"rej_{key}"):
                        update_editorial_status(art_id, "rejected")
                        st.rerun()
                with c4:
                    if st.button("📦 Arquivar", key=f"arch_{key}"):
                        update_editorial_status(art_id, "archived")
                        st.rerun()

                # Explicação do score
                exp = explain_score(art, scope)
                st.caption(f"💡 {exp['explanation']}")
                if exp["money_values_found"]:
                    # Escapa $ para não ser interpretado como LaTeX pelo Streamlit
                    vals = [v.replace("$", r"\$") for v in exp["money_values_found"]]
                    st.caption(f"💲 Valores: {', '.join(vals)}")

        st.divider()


def sidebar_controls() -> None:
    with st.sidebar:
        st.markdown("### ⚙️ Controles")
        if st.button("🔄 Atualizar"):
            st.rerun()
        auto = st.toggle("Auto-refresh")
        if auto:
            import time
            interval = st.select_slider("Intervalo", [30, 60, 120, 300], value=60)
            st.caption(f"Atualizando a cada {interval}s")
            time.sleep(interval)
            st.rerun()


def load_feeds() -> list[dict]:
    with open(FEEDS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f).get("feeds", [])


def save_feeds(feeds: list[dict]) -> None:
    with open(FEEDS_PATH, "w", encoding="utf-8") as f:
        yaml.dump({"feeds": feeds}, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
