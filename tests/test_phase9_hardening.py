"""Fase 9 — Testes de hardening, robustez e operações.

Cobre: migrations versionadas (schema_migrations), detecção de Chromium,
TTL cache, comando backup, e funções de auditoria com fallback.
"""
from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


# ── Migrations versionadas ────────────────────────────────────────────────────

class TestMigrationSQL:
    def test_migration_sql_e_dict_com_chaves_string(self):
        from news_radar.db import MIGRATION_SQL
        assert isinstance(MIGRATION_SQL, dict)
        for key in MIGRATION_SQL:
            assert isinstance(key, str), f"Chave deve ser str: {key!r}"

    def test_migration_sql_tem_entries_de_todas_as_fases(self):
        from news_radar.db import MIGRATION_SQL
        keys = list(MIGRATION_SQL.keys())
        assert any("editorial_status" in k for k in keys), "Falta migration de editorial_status"
        assert any("card_html_path" in k for k in keys), "Falta migration Fase 7"
        assert any("review_notes" in k for k in keys), "Falta migration Fase 8"

    def test_migration_sql_sem_drop_column(self):
        from news_radar.db import MIGRATION_SQL
        for key, stmt in MIGRATION_SQL.items():
            assert "DROP COLUMN" not in stmt.upper(), (
                f"Migration '{key}' contém DROP COLUMN — proibido sem aprovação"
            )

    def test_migration_sql_sem_drop_table(self):
        from news_radar.db import MIGRATION_SQL
        for key, stmt in MIGRATION_SQL.items():
            assert "DROP TABLE" not in stmt.upper(), (
                f"Migration '{key}' contém DROP TABLE — proibido sem aprovação"
            )

    def test_todas_migrations_tem_valor_nao_vazio(self):
        from news_radar.db import MIGRATION_SQL
        for key, stmt in MIGRATION_SQL.items():
            assert stmt.strip(), f"Migration '{key}' tem valor vazio"

    def test_chaves_de_migration_sao_unicas(self):
        from news_radar.db import MIGRATION_SQL
        keys = list(MIGRATION_SQL.keys())
        assert len(keys) == len(set(keys)), "Chaves duplicadas em MIGRATION_SQL"


# ── _ensure_datetime_columns com guard ───────────────────────────────────────

class TestEnsureDatetimeColumns:
    def test_nao_executa_alter_quando_ja_e_timestamptz(self):
        """Colunas já TIMESTAMPTZ não devem ser alteradas."""
        from news_radar.db import _ensure_datetime_columns, DATE_COLUMN_MIGRATIONS

        executed_alters = []

        class FakeCursor:
            def execute(self, q, p=None):
                if "ALTER TABLE" in q.upper():
                    executed_alters.append(q)

            def fetchone(self):
                # Simula: coluna já é TIMESTAMPTZ
                return {"data_type": "timestamp with time zone"}

        _ensure_datetime_columns(FakeCursor())
        assert executed_alters == [], (
            "Não deve emitir ALTER se coluna já é TIMESTAMPTZ"
        )

    def test_executa_alter_quando_tipo_e_texto(self):
        """Colunas TEXT precisam ser alteradas para TIMESTAMPTZ."""
        from news_radar.db import _ensure_datetime_columns

        executed_alters = []

        class FakeCursor:
            def execute(self, q, p=None):
                if "ALTER TABLE" in q.upper():
                    executed_alters.append(q)

            def fetchone(self):
                return {"data_type": "text"}

        _ensure_datetime_columns(FakeCursor())
        assert len(executed_alters) > 0, (
            "Deve emitir ALTER se coluna não é TIMESTAMPTZ"
        )

    def test_nao_altera_coluna_inexistente(self):
        """Coluna não existente (fetchone = None) não deve gerar ALTER."""
        from news_radar.db import _ensure_datetime_columns

        executed_alters = []

        class FakeCursor:
            def execute(self, q, p=None):
                if "ALTER TABLE" in q.upper():
                    executed_alters.append(q)

            def fetchone(self):
                return None  # Coluna não existe

        _ensure_datetime_columns(FakeCursor())
        assert executed_alters == []


# ── Detecção de Chromium ──────────────────────────────────────────────────────

class TestChromiumExecutable:
    def test_retorna_none_quando_nada_disponivel(self, monkeypatch):
        """Sem env vars e sem Chromium no PATH → None (usa bundled do Playwright)."""
        from news_radar import card_renderer

        monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", raising=False)
        monkeypatch.delenv("CHROMIUM_PATH", raising=False)
        monkeypatch.setattr("shutil.which", lambda name: None)

        result = card_renderer._chromium_executable()
        assert result is None

    def test_retorna_env_playwright_chromium_executable_path(self, monkeypatch, tmp_path):
        from news_radar import card_renderer

        fake_exec = tmp_path / "chromium"
        fake_exec.write_text("fake")
        monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", str(fake_exec))

        result = card_renderer._chromium_executable()
        assert result == str(fake_exec)

    def test_retorna_env_chromium_path(self, monkeypatch, tmp_path):
        from news_radar import card_renderer

        fake_exec = tmp_path / "chromium"
        fake_exec.write_text("fake")
        monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", raising=False)
        monkeypatch.setenv("CHROMIUM_PATH", str(fake_exec))

        result = card_renderer._chromium_executable()
        assert result == str(fake_exec)

    def test_ignora_env_que_nao_existe_como_arquivo(self, monkeypatch):
        from news_radar import card_renderer

        monkeypatch.setenv("CHROMIUM_PATH", "/nao/existe/chromium")
        monkeypatch.delenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", raising=False)
        monkeypatch.setattr("shutil.which", lambda name: None)

        result = card_renderer._chromium_executable()
        assert result is None


# ── TTL cache ─────────────────────────────────────────────────────────────────

class TestTTLCache:
    def test_funcao_retorna_resultado_do_cache(self):
        from news_radar.dashboard_queries import _ttl_cache

        call_count = {"n": 0}

        @_ttl_cache(seconds=60)
        def expensive(x):
            call_count["n"] += 1
            return x * 2

        assert expensive(5) == 10
        assert expensive(5) == 10  # do cache
        assert call_count["n"] == 1, "Função chamada mais vezes do que o esperado"

    def test_cache_expira_apos_ttl(self):
        from news_radar.dashboard_queries import _ttl_cache

        call_count = {"n": 0}

        @_ttl_cache(seconds=0)  # expira imediatamente
        def always_fresh(x):
            call_count["n"] += 1
            return x

        always_fresh(1)
        time.sleep(0.01)
        always_fresh(1)
        assert call_count["n"] == 2, "Cache com TTL=0 deve re-executar"

    def test_diferentes_argumentos_tem_entradas_separadas(self):
        from news_radar.dashboard_queries import _ttl_cache

        results = []

        @_ttl_cache(seconds=60)
        def fn(x):
            results.append(x)
            return x

        fn(1)
        fn(2)
        fn(1)  # do cache
        assert results == [1, 2]

    def test_cache_clear_limpa_entradas(self):
        from news_radar.dashboard_queries import _ttl_cache

        call_count = {"n": 0}

        @_ttl_cache(seconds=60)
        def fn():
            call_count["n"] += 1
            return 42

        fn()
        fn.cache_clear()
        fn()
        assert call_count["n"] == 2


# ── Comando backup ────────────────────────────────────────────────────────────

class TestBackupCommand:
    def test_retorna_error_quando_pg_dump_ausente(self, monkeypatch, capsys):
        import shutil
        import argparse
        from news_radar.cli import cmd_backup

        monkeypatch.setattr(shutil, "which", lambda name: None)

        args = argparse.Namespace(output=None)
        cmd_backup(args)

        captured = capsys.readouterr()
        import json
        result = json.loads(captured.out)
        assert result["ok"] is False
        assert "pg_dump" in result["error"].lower() or "manual" in result

    def test_backup_com_pg_dump_disponivel(self, monkeypatch, tmp_path, capsys):
        import shutil
        import subprocess
        import argparse
        from news_radar.cli import cmd_backup

        # Simula pg_dump disponível e funcionando
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/pg_dump" if name == "pg_dump" else None)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "-- PostgreSQL dump\n"
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: mock_result)

        output = str(tmp_path / "test_backup.sql")
        args = argparse.Namespace(output=output)
        cmd_backup(args)

        captured = capsys.readouterr()
        import json
        result = json.loads(captured.out)
        assert result["ok"] is True
        assert Path(output).exists()


# ── CLI: backup registrado no parser ─────────────────────────────────────────

class TestCLIParser:
    def test_backup_command_existe_no_parser(self):
        from news_radar.cli import build_parser
        parser = build_parser()
        # Verificar se o subparser 'backup' existe tentando fazer parse
        args = parser.parse_args(["backup"])
        assert hasattr(args, "func")

    def test_backup_aceita_argumento_output(self):
        from news_radar.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["backup", "--output", "meu_backup.sql"])
        assert args.output == "meu_backup.sql"

    def test_backup_output_opcional(self):
        from news_radar.cli import build_parser
        parser = build_parser()
        args = parser.parse_args(["backup"])
        assert args.output is None
