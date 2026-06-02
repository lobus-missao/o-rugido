"""
Testes do scheduler interno opcional (APScheduler).

Ref: docs/specs/12-n8n-decoupling.md — Etapa 1.1 e 1.2
"""
from __future__ import annotations

import os

from news_radar import scheduler as sched_mod

# ---------------------------------------------------------------------------
# _is_enabled() — lógica de ativação por env var
# ---------------------------------------------------------------------------


def test_scheduler_disabled_by_default(monkeypatch):
    """Scheduler desativado quando NEWS_RADAR_SCHEDULER não está definido."""
    monkeypatch.delenv("NEWS_RADAR_SCHEDULER", raising=False)
    assert sched_mod._is_enabled() is False


def test_scheduler_disabled_when_zero(monkeypatch):
    """Scheduler desativado quando NEWS_RADAR_SCHEDULER=0."""
    monkeypatch.setenv("NEWS_RADAR_SCHEDULER", "0")
    assert sched_mod._is_enabled() is False


def test_scheduler_disabled_when_false_string(monkeypatch):
    """Scheduler desativado quando NEWS_RADAR_SCHEDULER=false."""
    monkeypatch.setenv("NEWS_RADAR_SCHEDULER", "false")
    assert sched_mod._is_enabled() is False


def test_scheduler_enabled_when_one(monkeypatch):
    """Scheduler ativado quando NEWS_RADAR_SCHEDULER=1."""
    monkeypatch.setenv("NEWS_RADAR_SCHEDULER", "1")
    assert sched_mod._is_enabled() is True


def test_scheduler_enabled_when_true(monkeypatch):
    """Scheduler ativado quando NEWS_RADAR_SCHEDULER=true."""
    monkeypatch.setenv("NEWS_RADAR_SCHEDULER", "true")
    assert sched_mod._is_enabled() is True


def test_scheduler_enabled_when_yes(monkeypatch):
    """Scheduler ativado quando NEWS_RADAR_SCHEDULER=yes."""
    monkeypatch.setenv("NEWS_RADAR_SCHEDULER", "yes")
    assert sched_mod._is_enabled() is True


# ---------------------------------------------------------------------------
# create_scheduler() — jobs registrados corretamente
# ---------------------------------------------------------------------------


def test_create_scheduler_registers_two_jobs():
    sched = sched_mod.create_scheduler()
    job_ids = {j.id for j in sched.get_jobs()}

    assert job_ids == {"collect_and_rank", "dispatch_default"}


def test_create_scheduler_collect_job_is_interval():
    sched = sched_mod.create_scheduler()
    job = next(j for j in sched.get_jobs() if j.id == "collect_and_rank")
    assert "interval" in type(job.trigger).__name__.lower()


def test_create_scheduler_dispatch_job_is_cron():
    sched = sched_mod.create_scheduler()
    job = next(j for j in sched.get_jobs() if j.id == "dispatch_default")
    assert "cron" in type(job.trigger).__name__.lower()


def test_create_scheduler_respects_scope_env(monkeypatch):
    monkeypatch.setenv("NEWS_RADAR_DISPATCH_SCOPE", "piaui")
    sched = sched_mod.create_scheduler()
    job_ids = {j.id for j in sched.get_jobs()}
    assert "dispatch_default" in job_ids


# ---------------------------------------------------------------------------
# start_scheduler() — proteção de contexto de teste
# ---------------------------------------------------------------------------


def test_start_scheduler_returns_false_in_test_context():
    """start_scheduler() retorna False dentro de contexto pytest.

    PYTEST_CURRENT_TEST é definido pelo próprio pytest durante a execução,
    garantindo que o scheduler nunca inicie inadvertidamente em testes.
    """
    assert os.getenv("PYTEST_CURRENT_TEST") is not None, (
        "PYTEST_CURRENT_TEST deve estar definido durante execução pytest"
    )
    result = sched_mod.start_scheduler()
    assert result is False


def test_start_scheduler_returns_false_when_disabled(monkeypatch):
    """start_scheduler() retorna False quando NEWS_RADAR_SCHEDULER=0."""
    monkeypatch.setenv("NEWS_RADAR_SCHEDULER", "0")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    # Mesmo sem PYTEST_CURRENT_TEST, o scheduler não deve iniciar se desativado
    result = sched_mod.start_scheduler()
    assert result is False


# ---------------------------------------------------------------------------
# get_status() — retorno correto quando não iniciado
# ---------------------------------------------------------------------------


def test_get_status_not_running_when_scheduler_is_none(monkeypatch):
    """get_status() reporta running=False quando scheduler não foi iniciado."""
    monkeypatch.setattr(sched_mod, "_scheduler", None)
    status = sched_mod.get_status()
    assert status["running"] is False
    assert status["jobs"] == []


def test_get_status_includes_enabled_field(monkeypatch):
    """get_status() sempre inclui campo 'enabled' baseado no env var."""
    monkeypatch.setattr(sched_mod, "_scheduler", None)
    monkeypatch.setenv("NEWS_RADAR_SCHEDULER", "1")
    status = sched_mod.get_status()
    assert "enabled" in status
    assert status["enabled"] is True


def test_get_status_enabled_false_when_disabled(monkeypatch):
    """get_status() retorna enabled=False quando NEWS_RADAR_SCHEDULER não está definido."""
    monkeypatch.setattr(sched_mod, "_scheduler", None)
    monkeypatch.delenv("NEWS_RADAR_SCHEDULER", raising=False)
    status = sched_mod.get_status()
    assert status["enabled"] is False
