"""
Scheduler interno opcional — APScheduler BackgroundScheduler.

Ativação:  NEWS_RADAR_SCHEDULER=1  (no .env ou variável de ambiente)
Padrão:    desativado (NEWS_RADAR_SCHEDULER=0 ou não definido)

O n8n continua como scheduler principal enquanto esta variável não for ativada.
Ambos podem coexistir: o guard de idempotência em create_dispatch() garante
que o duplo disparo não resulte em mensagens duplicadas no Telegram.

⚠️  Aviso multi-worker:
    BackgroundScheduler é compatível APENAS com execução single-process.
    O docker-compose atual usa `python api_server.py` (Flask single-process)
    — não há risco nesta configuração.

    Se futuramente usar gunicorn com --workers N, cada worker iniciará
    um scheduler independente → N coletas e N dispatches paralelos.
    Solução para multi-worker (não implementada nesta fase):
      - APScheduler com job store PostgreSQL (exclusive locking), ou
      - Processo separado: `python -m news_radar.scheduler`, ou
      - gunicorn com --preload e --workers 1 para o processo de scheduler.
"""
from __future__ import annotations

import logging
import os
from typing import Any

_logger = logging.getLogger(__name__)

_scheduler = None  # instância BackgroundScheduler; None = não iniciado


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def _job_collect_and_rank() -> None:
    """Coleta RSS de todos os feeds e recalcula ranking. Roda a cada 30 minutos."""
    from .collector import collect_feeds
    from .ranker import rank_all

    _logger.info("Scheduler [collect_and_rank]: iniciando coleta RSS...")
    try:
        result = collect_feeds(limit_per_feed=30)
        _logger.info(
            "Scheduler [collect_and_rank]: coleta concluída — %d inseridos, %d atualizados",
            result.get("inserted", 0),
            result.get("updated", 0),
        )
    except Exception:
        _logger.exception("Scheduler [collect_and_rank]: erro na coleta RSS")

    _logger.info("Scheduler [collect_and_rank]: recalculando ranking...")
    try:
        count = rank_all()
        _logger.info(
            "Scheduler [collect_and_rank]: ranking recalculado para %d artigos", count
        )
    except Exception:
        _logger.exception("Scheduler [collect_and_rank]: erro no recálculo de ranking")


def _job_dispatch(edition: str, scope: str, top: int) -> None:
    """Disparo editorial de uma edição.

    O guard de idempotência em create_dispatch() bloqueia envio duplicado
    caso o n8n e o scheduler disparem simultaneamente.
    """
    from .dispatch import create_dispatch

    _logger.info("Scheduler [dispatch_%s]: iniciando scope=%s top=%d", edition, scope, top)
    try:
        created = create_dispatch(edition=edition, scope=scope, top=top)
        _logger.info(
            "Scheduler [dispatch_%s]: %d dispatch(es) criados", edition, len(created)
        )
    except Exception:
        _logger.exception("Scheduler [dispatch_%s]: erro no disparo", edition)


# ---------------------------------------------------------------------------
# Configuração e ciclo de vida
# ---------------------------------------------------------------------------


def _is_enabled() -> bool:
    """Retorna True se NEWS_RADAR_SCHEDULER=1 (ou true/yes/on)."""
    return os.getenv("NEWS_RADAR_SCHEDULER", "").lower() in {"1", "true", "yes", "on"}


def _in_test_context() -> bool:
    """Retorna True quando rodando dentro de pytest (PYTEST_CURRENT_TEST definido)."""
    return bool(os.getenv("PYTEST_CURRENT_TEST"))


def create_scheduler():
    """Cria e configura o scheduler com os 4 jobs padrão (não inicia).

    Configuração via variáveis de ambiente:
      NEWS_RADAR_DISPATCH_SCOPE  — scope do dispatch (padrão: piaui)
      NEWS_RADAR_DISPATCH_TOP    — top N artigos por edição (padrão: 3)
    """
    from apscheduler.schedulers.background import BackgroundScheduler

    scope = os.getenv("NEWS_RADAR_DISPATCH_SCOPE", "piaui")
    top = int(os.getenv("NEWS_RADAR_DISPATCH_TOP", "3"))

    sched = BackgroundScheduler(timezone="America/Fortaleza")

    sched.add_job(
        _job_collect_and_rank,
        "interval",
        minutes=30,
        id="collect_and_rank",
        replace_existing=True,
    )
    sched.add_job(
        _job_dispatch,
        "cron",
        args=["morning", scope, top],
        hour=6,
        minute=30,
        id="dispatch_morning",
        replace_existing=True,
    )
    sched.add_job(
        _job_dispatch,
        "cron",
        args=["noon", scope, top],
        hour=11,
        minute=30,
        id="dispatch_noon",
        replace_existing=True,
    )
    sched.add_job(
        _job_dispatch,
        "cron",
        args=["evening", scope, top],
        hour=17,
        minute=30,
        id="dispatch_evening",
        replace_existing=True,
    )

    return sched


def start_scheduler() -> bool:
    """Inicia o scheduler se habilitado e não rodando ainda.

    Retorna True se iniciou com sucesso, False caso contrário.
    É seguro chamar múltiplas vezes — não inicia duplicate.
    Não inicia em contexto de teste (PYTEST_CURRENT_TEST definido).
    """
    global _scheduler

    if _in_test_context():
        _logger.debug("Scheduler: contexto de teste detectado — não iniciando")
        return False

    if not _is_enabled():
        _logger.debug(
            "Scheduler: NEWS_RADAR_SCHEDULER != 1 — desativado. "
            "Defina NEWS_RADAR_SCHEDULER=1 para ativar."
        )
        return False

    if _scheduler is not None and _scheduler.running:
        _logger.warning("Scheduler: já está em execução — ignorando segunda chamada")
        return False

    _scheduler = create_scheduler()
    _scheduler.start()

    job_ids = [j.id for j in _scheduler.get_jobs()]
    _logger.info(
        "Scheduler interno iniciado. Jobs registrados: %s. "
        "Para desativar: NEWS_RADAR_SCHEDULER=0 e reiniciar.",
        job_ids,
    )
    return True


def stop_scheduler() -> bool:
    """Para o scheduler se estiver rodando. Retorna True se parou."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _logger.info("Scheduler interno parado.")
        _scheduler = None
        return True
    return False


def get_status() -> dict[str, Any]:
    """Retorna estado atual do scheduler.

    Nota: esta função retorna o estado do processo atual. Em configurações
    multi-processo (gunicorn), cada processo tem seu próprio estado.
    Para o estado real do scheduler, chamar via endpoint /api/scheduler/status
    dentro do mesmo processo onde o scheduler foi iniciado.
    """
    enabled = _is_enabled()

    if _scheduler is None or not _scheduler.running:
        return {
            "enabled": enabled,
            "running": False,
            "jobs": [],
        }

    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "next_run": next_run.isoformat() if next_run else None,
        })

    return {
        "enabled": enabled,
        "running": True,
        "jobs": jobs,
    }
