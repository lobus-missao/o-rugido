from __future__ import annotations

from datetime import timedelta

import streamlit as st
from components import EDITORIAL_LABELS

from o_rugido.core.config import TELEGRAM_BOT_TOKEN
from o_rugido.services.monitoring import (
    alerts,
    api_health,
    containers_health,
    db_health,
    host_health,
    internal_services_health,
    n8n_health,
    pipeline_health,
    serper_health,
    telegram_health,
)

st.set_page_config(page_title="Monitoramento", layout="wide")

st.title("Monitoramento")
st.caption("Estado dos serviços, pipeline e alertas ativos")


@st.cache_data(ttl=30, show_spinner=False)
def _load_all():
    return {
        "api": api_health(),
        "host": host_health(),
        "db": db_health(),
        "pipeline": pipeline_health(),
        "services": internal_services_health(),
        "telegram": telegram_health(TELEGRAM_BOT_TOKEN),
        "n8n": n8n_health(),
        "containers": containers_health(),
        "serper": serper_health(),
    }


if st.button("Atualizar"):
    _load_all.clear()
    st.rerun()

data = _load_all()
active_alerts = alerts(data["pipeline"], data["n8n"])

if active_alerts:
    for a in active_alerts:
        if a["level"] == "critical":
            st.error(a["message"])
        else:
            st.warning(a["message"])
else:
    st.success("Sem alertas ativos. Tudo verde.")

st.divider()


def _fmt_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    td = timedelta(seconds=int(seconds))
    days, rem = divmod(td.total_seconds(), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days >= 1:
        return f"{int(days)}d {int(hours)}h"
    if hours >= 1:
        return f"{int(hours)}h {int(minutes)}m"
    return f"{int(minutes)}m"


st.subheader("Sistema")
api = data["api"]
host = data["host"]
c1, c2, c3, c4 = st.columns(4)
c1.metric("API uptime", _fmt_duration(api["uptime_seconds"]))
c2.metric("API mem (MB)", api["memory_mb"])
c3.metric(
    "Host mem",
    f"{host['memory_percent']:.0f}%" if host["memory_percent"] else "—",
    delta=f"{host['memory_used_mb']:.0f} / {host['memory_total_mb']:.0f} MB"
    if host["memory_total_mb"] else None,
)
c4.metric(
    "Disco",
    f"{host['disk']['percent']:.0f}%" if host.get("disk") else "—",
    delta=f"{host['disk']['used_gb']} / {host['disk']['total_gb']} GB"
    if host.get("disk") else None,
)

c5, c6, c7, c8 = st.columns(4)
c5.metric("Load 1m", host["load_avg"]["1m"])
c6.metric("Load 5m", host["load_avg"]["5m"])
c7.metric(
    "Host CPU",
    f"{host['cpu_percent']:.1f}%" if host.get("cpu_percent") is not None else "—",
)
c8.metric("Host uptime", _fmt_duration(host["uptime_seconds"]))
st.caption(f"Métricas de host coletadas de: {host['scope']}")

st.divider()

st.subheader("Banco de dados")
db = data["db"]
if db.get("ok"):
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", "OK")
    c2.metric("Latência", f"{db['latency_ms']} ms")
    c3.metric("Tamanho", f"{db['db_size_mb']} MB")
    c4.metric("Conexões", db["active_connections"])
    st.caption(db.get("version", ""))
else:
    st.error(f"Postgres inacessível: {db.get('error')}")

st.divider()

st.subheader("Serviços internos")
svcs = data["services"]
cols = st.columns(len(svcs))
for (name, info), col in zip(svcs.items(), cols, strict=False):
    with col:
        ok = info.get("ok")
        if ok is None:
            st.metric(name, "n/a", help=info.get("note", ""))
        elif ok:
            st.metric(
                name,
                f"HTTP {info.get('status', '?')}",
                delta=f"{info.get('latency_ms', '?')} ms",
            )
        else:
            st.metric(name, "OFF", help=info.get("error", "")[:100])

st.divider()

st.subheader("Containers do stack")
cont = data["containers"]
if cont.get("ok") is None:
    st.caption(cont.get("note", "docker.sock indisponível"))
elif cont.get("ok"):
    for c in cont.get("containers", []):
        status = c["status"]
        icon = "🟢" if status == "running" else "🔴"
        st.markdown(f"- {icon} **{c['name']}** — `{status}` ({c['image']})")
else:
    st.error(cont.get("error", "erro no docker socket"))

st.divider()

st.subheader("APIs externas")
c_ext1, c_ext2 = st.columns(2)
with c_ext1:
    tg = data["telegram"]
    if tg.get("ok"):
        st.metric("Telegram", tg.get("username", "OK"), delta=f"{tg.get('latency_ms', '?')} ms")
    else:
        st.metric("Telegram", "OFF", help=tg.get("error") or str(tg.get("status")))
with c_ext2:
    sr = data["serper"]
    if sr.get("ok"):
        st.metric(
            "Serper API",
            f"HTTP {sr.get('status', '?')}",
            delta=f"{sr.get('latency_ms', '?')} ms",
        )
    else:
        st.metric("Serper API", "OFF", help=sr.get("error", "")[:100])

st.divider()

st.divider()

st.subheader("Pipeline editorial")
pl = data["pipeline"]
c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Última coleta OK",
    _fmt_duration(pl["last_collect_seconds_ago"]) + " atrás"
    if pl["last_collect_seconds_ago"] is not None else "—",
)
c2.metric("Erros feed 24h", pl["feed_errors_24h"])
c3.metric(
    "Última aprovação pendente",
    _fmt_duration(pl["last_pending_seconds_ago"]) + " atrás"
    if pl["last_pending_seconds_ago"] is not None else "—",
)
c4.metric(
    "Última publicação",
    _fmt_duration(pl["last_published_seconds_ago"]) + " atrás"
    if pl["last_published_seconds_ago"] is not None else "—",
)

by_status = pl["articles_by_status"]
if by_status:
    st.markdown("**Artigos por status editorial:**")
    n_cols = min(6, len(by_status))
    cols = st.columns(n_cols)
    for i, (status, n) in enumerate(sorted(by_status.items(), key=lambda x: -x[1])):
        label = EDITORIAL_LABELS.get(status, status)
        cols[i % n_cols].metric(label, n)

st.divider()

st.subheader("Workflows do n8n")
n8n = data["n8n"]
if not n8n.get("ok"):
    st.warning(f"n8n: {n8n.get('error', 'sem dados')}")
    st.caption(
        "Configure N8N_MONITOR_EMAIL e N8N_MONITOR_PASSWORD no .env "
        "pra habilitar o monitor do n8n."
    )
else:
    for wf in n8n.get("workflows", []):
        active_badge = "ativo" if wf.get("active") else "inativo"
        errors = wf.get("consecutive_errors", 0)
        with st.container(border=True):
            top = st.columns([3, 1, 1, 1])
            top[0].markdown(f"**{wf['name']}** — `{wf['id']}`")
            top[1].metric("Estado", active_badge)
            top[2].metric("Erros seguidos", errors)
            last_ok = wf.get("last_success")
            top[3].metric(
                "Última exec OK",
                str(last_ok)[:19].replace("T", " ") if last_ok else "—",
            )
            if wf.get("recent_executions"):
                st.markdown("Últimas execuções:")
                for e in wf["recent_executions"]:
                    when = str(e['started'])[:19].replace("T", " ")
                    st.markdown(f"- `{when}` **{e['status']}**")
