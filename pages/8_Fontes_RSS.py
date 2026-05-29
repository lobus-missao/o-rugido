"""Aba Fontes RSS — saúde e inteligência operacional das fontes."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

import streamlit as st
import feedparser
from news_radar.dash_utils import sidebar_controls, load_feeds, save_feeds, fmt_dt
from news_radar.dashboard_queries import source_health, sources_summary
from news_radar.sources import list_sources

st.set_page_config(page_title="Fontes RSS · News Radar", page_icon="📡", layout="wide")
sidebar_controls()
st.title("📡 Fontes RSS")

CLASS_ICON = {
    "quente":    "🔥",
    "relevante": "⭐",
    "normal":    "✅",
    "ruidosa":   "📢",
    "com_erro":  "⚠️",
    "instavel":  "❌",
    "inativa":   "💤",
}
CLASS_LABEL = {
    "quente":    "Fonte quente",
    "relevante": "Fonte relevante",
    "normal":    "Normal",
    "ruidosa":   "Fonte ruidosa",
    "com_erro":  "Com erro",
    "instavel":  "Instável",
    "inativa":   "Inativa",
}

# ── Métricas rápidas ──────────────────────────────────────────────────────────
feeds = load_feeds()
try:
    health = source_health()
    health_by_name = {h["source"]: h for h in health}
except Exception:
    health = []
    health_by_name = {}

try:
    db_summary = sources_summary()
except Exception:
    db_summary = {"total": 0, "enabled": 0, "with_error": 0, "by_scope": {}}

try:
    db_sources = list_sources()
    db_sources_by_name = {s["name"]: s for s in db_sources}
except Exception:
    db_sources = []
    db_sources_by_name = {}

enabled = sum(1 for f in feeds if f.get("enabled", True))
n_hot = sum(1 for h in health if h["classification"] == "quente")
n_err = sum(1 for h in health if h["classification"] in ("instavel", "com_erro"))

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("📡 Total feeds (yaml)", len(feeds))
c2.metric("✅ Ativos (yaml)", enabled)
c3.metric("🔥 Fontes quentes", n_hot)
c4.metric("⚠️ Com erro/instável", n_err)
c5.metric("📦 Registradas no banco", db_summary["total"],
          help="Fontes na tabela sources. Execute scripts/seed_sources.py para importar.")

# ── Filtros ───────────────────────────────────────────────────────────────────
col_f1, col_f2 = st.columns(2)
with col_f1:
    scope_filter = st.multiselect("Escopo", ["brasil", "piaui", "teresina"],
                                   default=["brasil", "piaui", "teresina"])
with col_f2:
    class_filter = st.multiselect("Classificação",
        list(CLASS_LABEL.keys()),
        default=list(CLASS_LABEL.keys()))

enabled_filter = st.radio("Mostrar", ["Todos", "Ativos", "Desativados"], horizontal=True)

st.divider()
st.subheader("Fontes")

feeds_changed = False
for i, feed in enumerate(feeds):
    name = feed["name"]
    scope = feed.get("scope", "brasil")
    trust = float(feed.get("trust", 0.5))
    is_enabled = feed.get("enabled", True)
    h = health_by_name.get(name, {})
    classification = h.get("classification", "inativa")

    # Aplica filtros
    if scope not in scope_filter:
        continue
    if classification not in class_filter:
        continue
    if enabled_filter == "Ativos" and not is_enabled:
        continue
    if enabled_filter == "Desativados" and is_enabled:
        continue

    cls_icon = CLASS_ICON.get(classification, "✅")
    scope_badge = {"brasil": "🇧🇷", "piaui": "🟣", "teresina": "🏙️"}.get(scope, "")
    total_arts = h.get("total_arts", 0)
    high_arts = h.get("high_arts", 0)
    avg_score = h.get("avg_score", 0)
    error_rate = h.get("error_rate", 0)
    last_run = fmt_dt(h.get("last_run"))
    collected = h.get("total_collected", 0)

    header = (
        f"{cls_icon} {scope_badge} **{name}** · "
        f"{collected} coletados · {high_arts} alta/crítica · "
        f"★{avg_score:.1f} · {last_run}"
    )

    with st.expander(header):
        col_a, col_b, col_c = st.columns([3, 1, 1])

        with col_a:
            st.caption(f"URL: `{feed['url']}`")
            if h.get("last_error"):
                st.caption(f"Último erro: _{str(h['last_error'])[:100]}_")
            st.markdown(f"**Classificação:** {cls_icon} {CLASS_LABEL.get(classification, classification)}")
            if error_rate:
                st.markdown(f"**Taxa de erro:** {error_rate}%")

            # Dados da tabela sources (Fase 2)
            db_src = db_sources_by_name.get(name)
            if db_src:
                db_status = db_src.get("last_status") or "—"
                db_errors = db_src.get("error_count", 0)
                db_last = fmt_dt(db_src.get("last_run_at"), 16)
                status_icon = "✅" if db_status == "ok" else ("❌" if db_status == "error" else "⬜")
                st.caption(
                    f"**Banco:** {status_icon} status={db_status} · "
                    f"erros acumulados={db_errors} · última atualização={db_last or '—'}"
                )

        with col_b:
            new_enabled = st.toggle("Ativo", value=is_enabled, key=f"tog_{i}_{name}")
            if new_enabled != is_enabled:
                feeds[i]["enabled"] = new_enabled
                feeds_changed = True

            new_trust = st.slider("Trust", 0.0, 1.0, value=trust, step=0.05,
                                  key=f"trust_{i}_{name}")
            if abs(new_trust - trust) > 0.001:
                feeds[i]["trust"] = round(new_trust, 2)
                feeds_changed = True

        with col_c:
            st.caption(f"Escopo: `{scope}`")
            st.caption(f"Artigos relevantes: {h.get('relevant_arts',0)}")

            if st.button("🔍 Testar", key=f"test_{i}_{name}"):
                with st.spinner("Testando..."):
                    try:
                        parsed = feedparser.parse(feed["url"])
                        n = len(parsed.entries)
                        bozo = getattr(parsed, "bozo", False)
                        exc = str(getattr(parsed, "bozo_exception", ""))[:60]
                        if n > 0:
                            st.success(f"✅ {n} entradas" + (f" (aviso: {exc})" if bozo else ""))
                        else:
                            st.warning(f"Sem entradas. {exc}")
                    except Exception as e:
                        st.error(f"❌ {e}")

            if st.button("🗑️ Remover", key=f"del_{i}_{name}", type="secondary"):
                feeds.pop(i)
                save_feeds(feeds)
                st.success(f"**{name}** removido.")
                st.rerun()

if feeds_changed:
    save_feeds(feeds)
    st.toast("Feeds salvos!", icon="💾")

# ── Adicionar novo feed ───────────────────────────────────────────────────────
st.divider()
st.subheader("➕ Adicionar feed")
with st.form("add_feed", clear_on_submit=True):
    col_n1, col_n2 = st.columns(2)
    with col_n1:
        new_name = st.text_input("Nome da fonte")
        new_url = st.text_input("URL do RSS")
    with col_n2:
        new_scope = st.selectbox("Escopo", ["brasil", "piaui", "teresina"])
        new_trust = st.slider("Trust", 0.0, 1.0, 0.65, 0.05)
    if st.form_submit_button("Adicionar"):
        if not new_name or not new_url:
            st.warning("Nome e URL obrigatórios.")
        elif any(f["name"] == new_name for f in feeds):
            st.warning(f"Já existe um feed com nome **{new_name}**.")
        else:
            feeds.append({"name": new_name, "url": new_url, "scope": new_scope,
                          "trust": new_trust, "enabled": True})
            save_feeds(feeds)
            st.success(f"Feed **{new_name}** adicionado!")
            st.rerun()

# ── Monitoramento via Banco (tabela sources) ──────────────────────────────────
st.divider()
st.subheader("📦 Monitoramento via Banco (tabela sources)")

if not db_sources:
    st.info(
        "A tabela `sources` está vazia. "
        "Execute `python scripts/seed_sources.py` para importar as fontes do `feeds.yaml`. "
        "Após a importação, o monitoramento por coleta aparecerá aqui."
    )
else:
    db_err = db_summary.get("with_error", 0)
    db_enabled = db_summary.get("enabled", 0)
    db_total = db_summary.get("total", 0)

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total no banco", db_total)
    mc2.metric("Habilitadas", db_enabled)
    mc3.metric("Com erro acumulado", db_err)

    # Filtros para a tabela sources
    col_sf1, col_sf2 = st.columns(2)
    with col_sf1:
        db_scope_filter = st.multiselect(
            "Escopo (banco)", ["brasil", "piaui", "teresina"],
            default=["brasil", "piaui", "teresina"], key="db_scope"
        )
    with col_sf2:
        db_status_filter = st.multiselect(
            "Status (banco)", ["ok", "error", "—"],
            default=["ok", "error", "—"], key="db_status"
        )

    import pandas as pd
    rows = []
    for s in db_sources:
        last_status = s.get("last_status") or "—"
        if s.get("scope") not in db_scope_filter:
            continue
        if last_status not in db_status_filter:
            continue
        rows.append({
            "Nome": s["name"],
            "Escopo": s.get("scope", ""),
            "Tipo": s.get("source_type", "rss"),
            "Habilitada": "✅" if s.get("enabled") else "❌",
            "Status": last_status,
            "Erros": s.get("error_count", 0),
            "Última atualização": fmt_dt(s.get("last_run_at"), 16) or "—",
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, height=350)
    else:
        st.info("Nenhuma fonte corresponde aos filtros selecionados.")
