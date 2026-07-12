from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import psutil
import requests

from o_rugido.core.db import connect

_START = time.time()

# Bind read-only do /proc do host, quando disponivel no compose
HOST_PROC = os.getenv("HOST_PROC", "/host/proc")


def _read_first_line(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.readline().strip()
    except (OSError, FileNotFoundError):
        return None


def api_health() -> dict[str, Any]:
    """Uptime, mem e cpu do processo Flask."""
    proc = psutil.Process(os.getpid())
    with proc.oneshot():
        mem = proc.memory_info().rss / (1024 * 1024)
        cpu = proc.cpu_percent(interval=None)
    return {
        "uptime_seconds": int(time.time() - _START),
        "memory_mb": round(mem, 1),
        "cpu_percent": round(cpu, 1),
        "pid": proc.pid,
    }


_CPU_LAST: dict[str, Any] = {"idle": None, "total": None}


def _read_cpu_stat(proc_root: str) -> tuple[int, int] | None:
    """Retorna (idle, total) do /proc/stat pra calculo de CPU."""
    line = _read_first_line(f"{proc_root}/stat")
    if not line or not line.startswith("cpu "):
        return None
    fields = [int(x) for x in line.split()[1:]]
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    total = sum(fields)
    return idle, total


def host_health() -> dict[str, Any]:
    """Metricas do host (via bind /proc). Se /host/proc nao existir,
    devolve metricas do proprio container (que ja e util)."""
    proc_root = HOST_PROC if os.path.isdir(HOST_PROC) else "/proc"
    scope = "host" if proc_root == HOST_PROC else "container"

    loadavg_raw = _read_first_line(f"{proc_root}/loadavg") or "0 0 0"
    parts = loadavg_raw.split()
    load_1, load_5, load_15 = (float(p) for p in parts[:3])

    uptime_seconds = 0
    uptime_raw = _read_first_line(f"{proc_root}/uptime")
    if uptime_raw:
        uptime_seconds = int(float(uptime_raw.split()[0]))

    mem_total = mem_avail = 0
    try:
        with open(f"{proc_root}/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    mem_avail = int(line.split()[1]) * 1024
                if mem_total and mem_avail:
                    break
    except OSError:
        pass

    # CPU: delta entre chamadas
    cpu_percent = None
    cur = _read_cpu_stat(proc_root)
    if cur and _CPU_LAST["idle"] is not None:
        idle_delta = cur[0] - _CPU_LAST["idle"]
        total_delta = cur[1] - _CPU_LAST["total"]
        if total_delta > 0:
            cpu_percent = round(100 * (1 - idle_delta / total_delta), 1)
    if cur:
        _CPU_LAST["idle"], _CPU_LAST["total"] = cur

    # Disco: sempre olha o filesystem do container (/ mount)
    try:
        disk = psutil.disk_usage("/")
        disk_info = {
            "total_gb": round(disk.total / (1024**3), 1),
            "used_gb": round(disk.used / (1024**3), 1),
            "percent": disk.percent,
        }
    except Exception:
        disk_info = None

    return {
        "scope": scope,
        "load_avg": {"1m": load_1, "5m": load_5, "15m": load_15},
        "cpu_percent": cpu_percent,
        "uptime_seconds": uptime_seconds,
        "memory_total_mb": round(mem_total / (1024**2), 0) if mem_total else 0,
        "memory_used_mb": round((mem_total - mem_avail) / (1024**2), 0) if mem_total else 0,
        "memory_percent": round(
            100 * (mem_total - mem_avail) / mem_total, 1
        ) if mem_total else 0,
        "disk": disk_info,
    }


def containers_health() -> dict[str, Any]:
    """Status dos containers via docker socket (bind /var/run/docker.sock).
    Se socket nao disponivel, retorna ok=None."""
    sock = "/var/run/docker.sock"
    if not os.path.exists(sock):
        return {"ok": None, "note": "docker.sock nao bindado no container"}
    try:
        import docker
        client = docker.DockerClient(base_url=f"unix://{sock}")
        containers = client.containers.list(all=True)
        summary = []
        for c in containers:
            summary.append({
                "name": c.name,
                "status": c.status,
                "image": c.image.tags[0] if c.image.tags else c.image.short_id,
            })
        return {"ok": True, "containers": summary}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def serper_health() -> dict[str, Any]:
    """Check leve da Serper API — só ping na raiz, sem consumir quota."""
    try:
        t0 = time.time()
        r = requests.get("https://google.serper.dev/", timeout=5)
        return {
            "ok": r.status_code < 500,
            "status": r.status_code,
            "latency_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}


def db_health() -> dict[str, Any]:
    """Postgres: connect, tamanho, conexoes ativas."""
    try:
        t0 = time.time()
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            latency_ms = int((time.time() - t0) * 1000)

            cur.execute(
                "SELECT pg_database_size(current_database()) / (1024*1024) AS mb"
            )
            db_size_mb = int(cur.fetchone()["mb"] or 0)

            cur.execute(
                "SELECT count(*) AS n FROM pg_stat_activity "
                "WHERE datname = current_database()"
            )
            active_conns = int(cur.fetchone()["n"] or 0)

            cur.execute("SELECT version()")
            version = (cur.fetchone()["version"] or "").split(" on ")[0]

        return {
            "ok": True,
            "latency_ms": latency_ms,
            "db_size_mb": db_size_mb,
            "active_connections": active_conns,
            "version": version,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def pipeline_health() -> dict[str, Any]:
    """Estado do pipeline editorial (via banco)."""
    now = datetime.now(timezone.utc)
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(finished_at) AS last FROM feed_runs WHERE status = 'ok'"
        )
        last_collect_ok = cur.fetchone()["last"]

        cur.execute(
            "SELECT COUNT(*) AS n FROM feed_runs "
            "WHERE status = 'error' AND finished_at > NOW() - INTERVAL '24 hours'"
        )
        errors_24h = int(cur.fetchone()["n"] or 0)

        cur.execute(
            "SELECT MAX(updated_at) AS last FROM articles "
            "WHERE editorial_status = 'pending_approval'"
        )
        last_pending = cur.fetchone()["last"]

        cur.execute(
            "SELECT MAX(updated_at) AS last FROM articles "
            "WHERE editorial_status = 'published'"
        )
        last_published = cur.fetchone()["last"]

        cur.execute(
            "SELECT editorial_status, COUNT(*) AS n FROM articles GROUP BY editorial_status"
        )
        by_status = {r["editorial_status"]: int(r["n"]) for r in cur.fetchall()}

    def _seconds_ago(dt):
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int((now - dt).total_seconds())

    return {
        "last_collect_ok": last_collect_ok.isoformat() if last_collect_ok else None,
        "last_collect_seconds_ago": _seconds_ago(last_collect_ok),
        "feed_errors_24h": errors_24h,
        "last_pending_approval": last_pending.isoformat() if last_pending else None,
        "last_pending_seconds_ago": _seconds_ago(last_pending),
        "last_published": last_published.isoformat() if last_published else None,
        "last_published_seconds_ago": _seconds_ago(last_published),
        "articles_by_status": by_status,
    }


def http_probe(url: str, timeout: int = 5) -> dict[str, Any]:
    """Check simples HTTP GET.

    Se o hostname não resolve (rodando fora da docker network), devolve
    ok=None com note explicativo — evita mostrar 'OFF vermelho' enganoso
    em dev local.
    """
    try:
        t0 = time.time()
        r = requests.get(url, timeout=timeout, allow_redirects=False)
        return {
            "ok": r.status_code < 500,
            "status": r.status_code,
            "latency_ms": int((time.time() - t0) * 1000),
        }
    except requests.exceptions.ConnectionError as e:
        msg = str(e)
        if "NameResolutionError" in msg or "getaddrinfo failed" in msg:
            return {"ok": None, "status": "n/a", "note": "hostname fora da rede docker"}
        return {"ok": False, "error": msg[:150]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}


def internal_services_health() -> dict[str, Any]:
    """Confere containers vizinhos do stack via HTTP interno."""
    return {
        "n8n": http_probe("http://n8n:5678/healthz", timeout=3),
        "dashboard": http_probe("http://dashboard:8501/_stcore/health", timeout=3),
        "searxng": http_probe("http://searxng:8080/", timeout=3),
    }


def telegram_health(token: str) -> dict[str, Any]:
    """Confere bot Telegram via getMe. Nao cacheia — chame com moderacao."""
    if not token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN vazio"}
    try:
        t0 = time.time()
        r = requests.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=5,
        )
        latency = int((time.time() - t0) * 1000)
        if r.ok:
            data = r.json()
            return {
                "ok": data.get("ok", False),
                "latency_ms": latency,
                "username": data.get("result", {}).get("username"),
            }
        return {"ok": False, "status": r.status_code, "latency_ms": latency}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}


_N8N_SESSION: dict[str, Any] = {"cookies": None, "expires": 0}


def _n8n_login(base_url: str, email: str, password: str) -> Any | None:
    """Faz login no n8n e cacheia cookie por ~50 min."""
    if _N8N_SESSION["cookies"] and time.time() < _N8N_SESSION["expires"]:
        return _N8N_SESSION["cookies"]
    try:
        r = requests.post(
            f"{base_url}/rest/login",
            json={"emailOrLdapLoginId": email, "password": password},
            timeout=5,
        )
        if r.ok:
            _N8N_SESSION["cookies"] = r.cookies
            _N8N_SESSION["expires"] = time.time() + 50 * 60
            return r.cookies
    except Exception:
        pass
    return None


def n8n_health(
    base_url: str | None = None,
    email: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    """Estado do n8n: workflows ativos, ultimas execucoes por workflow."""
    base_url = base_url or os.getenv("N8N_MONITOR_URL", "http://n8n:5678")
    email = email or os.getenv("N8N_MONITOR_EMAIL", "")
    password = password or os.getenv("N8N_MONITOR_PASSWORD", "")

    if not email or not password:
        return {"ok": False, "error": "N8N_MONITOR_EMAIL/PASSWORD nao configurados"}

    cookies = _n8n_login(base_url, email, password)
    if not cookies:
        return {"ok": False, "error": "login no n8n falhou"}

    try:
        wf_resp = requests.get(
            f"{base_url}/rest/workflows",
            cookies=cookies,
            timeout=5,
        )
        workflows = wf_resp.json().get("data", []) if wf_resp.ok else []

        exec_resp = requests.get(
            f"{base_url}/rest/executions?limit=50",
            cookies=cookies,
            timeout=5,
        )
        executions = exec_resp.json().get("data", {}) if exec_resp.ok else {}
        results = executions.get("results", executions if isinstance(executions, list) else [])
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

    by_workflow: dict[str, dict[str, Any]] = {}
    for wf in workflows:
        wf_id = wf.get("id")
        by_workflow[wf_id] = {
            "id": wf_id,
            "name": wf.get("name"),
            "active": wf.get("active"),
            "last_success": None,
            "last_error": None,
            "consecutive_errors": 0,
            "recent_executions": [],
        }

    # Ordena execucoes desc, calcula erros consecutivos por workflow
    for exec_ in results:
        wf_id = exec_.get("workflowId")
        if wf_id not in by_workflow:
            continue
        entry = by_workflow[wf_id]
        entry["recent_executions"].append({
            "id": exec_.get("id"),
            "status": exec_.get("status"),
            "started": exec_.get("startedAt"),
            "stopped": exec_.get("stoppedAt"),
        })

    for entry in by_workflow.values():
        found_success = False
        for e in entry["recent_executions"][:20]:
            if e["status"] == "success":
                if entry["last_success"] is None:
                    entry["last_success"] = e["started"]
                found_success = True
                if entry["consecutive_errors"] == 0:
                    pass
                else:
                    break
            elif e["status"] in ("error", "crashed", "failed"):
                if entry["last_error"] is None:
                    entry["last_error"] = e["started"]
                if not found_success:
                    entry["consecutive_errors"] += 1
        entry["recent_executions"] = entry["recent_executions"][:5]

    return {"ok": True, "workflows": list(by_workflow.values())}


def send_telegram_alert(text: str, chat_id: str, token: str) -> bool:
    """Manda mensagem simples pro chat via bot Telegram."""
    if not chat_id or not token:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        return r.ok
    except Exception:
        return False


def dispatch_critical_alerts(
    active_alerts: list[dict[str, Any]],
    chat_id: str,
    token: str,
) -> dict[str, Any]:
    """Envia alerts com level=critical pro chat Telegram do editor.

    Evita spam: registra ultimo alerta enviado por mensagem e so re-envia
    depois de 1h. Cache em memoria (reseta a cada restart do processo)."""
    sent = 0
    now = time.time()
    for a in active_alerts:
        if a.get("level") != "critical":
            continue
        key = a["message"]
        last = _ALERT_SENT.get(key, 0)
        if now - last < 3600:
            continue
        msg = f"🚨 *Portal O Rugido — Alerta*\n\n{a['message']}"
        if send_telegram_alert(msg, chat_id, token):
            _ALERT_SENT[key] = now
            sent += 1
    return {"critical_alerts": sum(1 for a in active_alerts if a.get("level") == "critical"), "sent": sent}


_ALERT_SENT: dict[str, float] = {}


def alerts(pipeline: dict[str, Any], n8n_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Deriva alertas a partir das metricas coletadas."""
    out: list[dict[str, Any]] = []

    lc = pipeline.get("last_collect_seconds_ago")
    if lc is None:
        out.append({"level": "warning", "message": "Nenhuma coleta bem-sucedida registrada"})
    elif lc > 8 * 3600:
        out.append({
            "level": "critical",
            "message": f"Coleta parada ha {lc // 3600}h — cron do n8n com problema?",
        })

    if pipeline.get("feed_errors_24h", 0) > 5:
        out.append({
            "level": "warning",
            "message": f"{pipeline['feed_errors_24h']} erros em feed_runs nas ultimas 24h",
        })

    lp = pipeline.get("last_published_seconds_ago")
    if lp is not None and lp > 24 * 3600:
        out.append({
            "level": "warning",
            "message": f"Nenhuma publicacao ha {lp // 3600}h",
        })

    if n8n_data.get("ok"):
        for wf in n8n_data.get("workflows", []):
            if wf.get("consecutive_errors", 0) >= 3:
                out.append({
                    "level": "critical",
                    "message": (
                        f"Workflow '{wf['name']}' com {wf['consecutive_errors']} "
                        "execucoes consecutivas em erro"
                    ),
                })

    return out
