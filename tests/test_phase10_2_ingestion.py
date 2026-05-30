"""
Testes da Fase 10.2 — Ingestão: scraped_pages → articles.

Critérios de aceite:
- build_article_from_scraped_page com dados completos
- fallback quando published_at ausente
- erro quando title ausente
- erro quando url ausente
- ingestão dry-run não persiste dados no banco
- ingestão ignora página já ingerida (ingestion_status != pending)
- ingestão não duplica articles por canonical_url
- marca scraped_page como ingested após inserção
- marca scraped_page com erro quando ingestão falha
- CLI ingest-scraping existe e aceita argumentos
- dashboard queries retornam fallback seguro sem banco
- migrations v10.2 têm chaves únicas
- insert_scraped_page aceita content_text
"""
from __future__ import annotations

import json
import os
import sys
from datetime import timezone, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

DB_URL = os.getenv("TEST_DATABASE_URL", "")
requires_db = pytest.mark.skipif(not DB_URL, reason="TEST_DATABASE_URL não configurado")


# ══════════════════════════════════════════════════════════════════════════════
# 1. Migrations e schema
# ══════════════════════════════════════════════════════════════════════════════

def test_v10_2_migration_keys_unique():
    """MIGRATION_SQL não pode ter chaves duplicadas."""
    from news_radar.db import MIGRATION_SQL
    keys = list(MIGRATION_SQL.keys())
    assert len(keys) == len(set(keys)), "MIGRATION_SQL contém chaves duplicadas"


def test_v10_2_migration_keys_exist():
    """Todas as migrations da Fase 10.2 devem estar no dict."""
    from news_radar.db import MIGRATION_SQL
    expected = [
        "v10_2_scraped_pages_content_text",
        "v10_2_scraped_pages_ingestion_status",
        "v10_2_scraped_pages_article_id",
        "v10_2_scraped_pages_ingestion_error",
        "v10_2_scraped_pages_ingested_at",
        "v10_2_scraped_pages_ingestion_idx",
        "v10_2_scraped_pages_article_idx",
    ]
    for key in expected:
        assert key in MIGRATION_SQL, f"Migration ausente: {key}"


def test_v10_2_migration_sql_are_strings():
    """Cada migration v10.2 deve ser uma string SQL válida."""
    from news_radar.db import MIGRATION_SQL
    for key, sql in MIGRATION_SQL.items():
        if key.startswith("v10_2_"):
            assert isinstance(sql, str) and len(sql) > 10, f"SQL inválido para {key}"


# ══════════════════════════════════════════════════════════════════════════════
# 2. build_article_from_scraped_page
# ══════════════════════════════════════════════════════════════════════════════

def _make_page(**kwargs) -> dict:
    """Fábrica de scraped_page para testes."""
    base = {
        "id": 42,
        "source_id": 1,
        "run_id": 10,
        "url": "https://g1.globo.com/pi/noticia/2026/05/30/teste.ghtml",
        "title": "Prefeita anuncia obras em Teresina",
        "content_text": "A prefeita anunciou nesta terça-feira obras de pavimentação.",
        "published_at": datetime(2026, 5, 30, 10, 0, tzinfo=timezone.utc),
        "fetched_at": datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc),
        "extraction_status": "ok",
        "ingestion_status": "pending",
        "source_name": "G1 Piauí",
        "source_scope": "piaui",
        "source_trust": 0.8,
    }
    base.update(kwargs)
    return base


def test_build_article_completo():
    """Campos obrigatórios preenchidos corretamente."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page()
    art = build_article_from_scraped_page(page)
    assert art is not None
    assert art["title"] == "Prefeita anuncia obras em Teresina"
    assert art["canonical_url"].startswith("https://")
    assert art["source"] == "G1 Piauí"
    assert art["source_scope"] == "piaui"
    assert float(art["source_trust"]) == 0.8
    assert art["id"] and len(art["id"]) > 0
    assert art["title_signature"] and len(art["title_signature"]) > 0
    assert art["raw_json"] is not None
    assert "auto_score_brasil" in art
    assert "final_score_brasil" in art


def test_build_article_summary_from_content():
    """summary usa content_text quando disponível."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page(content_text="Texto importante da notícia sobre Teresina.")
    art = build_article_from_scraped_page(page)
    assert "Texto importante" in art["summary"]


def test_build_article_sem_content_text():
    """Sem content_text, summary e content ficam vazios."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page(content_text=None)
    art = build_article_from_scraped_page(page)
    assert art is not None
    assert art["summary"] == ""
    assert art["content"] == ""


def test_build_article_fallback_published_at():
    """Sem published_at, usa fetched_at como fallback."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
    page = _make_page(published_at=None, fetched_at=now)
    art = build_article_from_scraped_page(page)
    assert art["published_at"] == now


def test_build_article_sem_published_at_e_fetched_at():
    """Sem datas, published_at fica None."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page(published_at=None, fetched_at=None)
    art = build_article_from_scraped_page(page)
    assert art["published_at"] is None


def test_build_article_title_vazio_levanta_erro():
    """title vazio deve levantar ValueError."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page(title="")
    with pytest.raises(ValueError, match="title"):
        build_article_from_scraped_page(page)


def test_build_article_title_none_levanta_erro():
    """title None deve levantar ValueError."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page(title=None)
    with pytest.raises(ValueError, match="title"):
        build_article_from_scraped_page(page)


def test_build_article_url_vazio_levanta_erro():
    """url vazio deve levantar ValueError."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page(url="")
    with pytest.raises(ValueError, match="url"):
        build_article_from_scraped_page(page)


def test_build_article_raw_json_contem_origem():
    """raw_json deve registrar origem como 'scraping'."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page()
    art = build_article_from_scraped_page(page)
    raw = json.loads(art["raw_json"])
    assert raw.get("origin") == "scraping"
    assert raw.get("scraped_page_id") == 42


def test_build_article_scope_fallback():
    """Sem source_scope, usa 'brasil'."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page(source_scope=None, source_name=None)
    art = build_article_from_scraped_page(page)
    assert art["source_scope"] == "brasil"


def test_build_article_source_name_fallback():
    """Sem source_name, source fica 'scraping'."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page(source_name=None)
    art = build_article_from_scraped_page(page)
    assert art["source"] == "scraping"


def test_build_article_with_source_override():
    """source dict sobrepõe campos do page."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page(source_name="fallback", source_scope="brasil")
    source = {"name": "Portal Correto", "scope": "teresina", "trust": 0.9}
    art = build_article_from_scraped_page(page, source=source)
    assert art["source"] == "Portal Correto"
    assert art["source_scope"] == "teresina"
    assert float(art["source_trust"]) == 0.9


def test_build_article_id_deterministico():
    """O mesmo page deve gerar o mesmo id."""
    from news_radar.scraper.ingestion import build_article_from_scraped_page
    page = _make_page()
    art1 = build_article_from_scraped_page(page)
    art2 = build_article_from_scraped_page(page)
    assert art1["id"] == art2["id"]


# ══════════════════════════════════════════════════════════════════════════════
# 3. ingest_scraped_pages — modo dry-run (sem banco)
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_dry_run_sem_paginas():
    """dry_run sem páginas elegíveis retorna eligible=0 sem erros."""
    from news_radar.scraper.ingestion import ingest_scraped_pages
    with patch("news_radar.scraper.ingestion.get_eligible_pages", return_value=[]):
        result = ingest_scraped_pages(dry_run=True, limit=10)
    assert result["eligible"] == 0
    assert result["errors"] == 0
    assert result["dry_run"] is True


def test_ingest_dry_run_nao_chama_upsert():
    """dry_run nunca chama upsert_article."""
    from news_radar.scraper.ingestion import ingest_scraped_pages
    page = _make_page()
    with patch("news_radar.scraper.ingestion.get_eligible_pages", return_value=[page]), \
         patch("news_radar.scraper.ingestion.connect") as mock_conn, \
         patch("news_radar.scraper.ingestion.upsert_article") as mock_upsert, \
         patch("news_radar.scraper.ingestion.mark_scraped_page_ingested") as mock_mark:
        # Simula cursor para verificação de duplicata
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = None
        mock_conn_ctx = MagicMock()
        mock_conn_ctx.__enter__ = lambda s: mock_conn_ctx
        mock_conn_ctx.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_conn_ctx

        result = ingest_scraped_pages(dry_run=True, limit=10)

    mock_upsert.assert_not_called()
    mock_mark.assert_not_called()
    assert result["dry_run"] is True


def test_ingest_dry_run_conta_duplicata():
    """dry_run incrementa skipped_duplicate quando URL já existe em articles."""
    from news_radar.scraper.ingestion import ingest_scraped_pages
    page = _make_page()
    with patch("news_radar.scraper.ingestion.get_eligible_pages", return_value=[page]), \
         patch("news_radar.scraper.ingestion.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = {"id": "existing_id"}
        mock_conn_ctx = MagicMock()
        mock_conn_ctx.__enter__ = lambda s: mock_conn_ctx
        mock_conn_ctx.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_conn_ctx

        result = ingest_scraped_pages(dry_run=True, limit=10)

    assert result["skipped_duplicate"] == 1
    assert result["inserted"] == 0


def test_ingest_dry_run_conta_seria_inserido():
    """dry_run incrementa inserted quando URL não existe em articles."""
    from news_radar.scraper.ingestion import ingest_scraped_pages
    page = _make_page()
    with patch("news_radar.scraper.ingestion.get_eligible_pages", return_value=[page]), \
         patch("news_radar.scraper.ingestion.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = None
        mock_conn_ctx = MagicMock()
        mock_conn_ctx.__enter__ = lambda s: mock_conn_ctx
        mock_conn_ctx.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_conn_ctx

        result = ingest_scraped_pages(dry_run=True, limit=10)

    assert result["inserted"] == 1
    assert result["skipped_duplicate"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# 4. ingest_scraped_pages — tratamento de erros
# ══════════════════════════════════════════════════════════════════════════════

def test_ingest_erro_nao_para_lote():
    """Erro em uma página não para o processamento das demais."""
    from news_radar.scraper.ingestion import ingest_scraped_pages
    page_ok = _make_page(id=1)
    page_bad = _make_page(id=2, title="")  # vai causar ValueError

    with patch("news_radar.scraper.ingestion.get_eligible_pages",
               return_value=[page_bad, page_ok]), \
         patch("news_radar.scraper.ingestion.connect") as mock_conn, \
         patch("news_radar.scraper.ingestion.upsert_article", return_value=True), \
         patch("news_radar.scraper.ingestion.mark_scraped_page_ingested"), \
         patch("news_radar.scraper.ingestion.mark_scraped_page_ingestion_error"):
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx = MagicMock()
        mock_conn_ctx.__enter__ = lambda s: mock_conn_ctx
        mock_conn_ctx.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_conn_ctx

        result = ingest_scraped_pages(dry_run=False, limit=10)

    assert result["errors"] == 1
    assert result["inserted"] == 1
    assert len(result["error_details"]) == 1


def test_ingest_real_chama_upsert_e_mark_inline():
    """Ingestão real chama upsert_article e faz o marking inline na mesma conn."""
    from news_radar.scraper.ingestion import ingest_scraped_pages
    page = _make_page()

    with patch("news_radar.scraper.ingestion.get_eligible_pages", return_value=[page]), \
         patch("news_radar.scraper.ingestion.connect") as mock_conn, \
         patch("news_radar.scraper.ingestion.upsert_article", return_value=True) as mock_upsert, \
         patch("news_radar.scraper.ingestion.mark_scraped_page_ingestion_error") as mock_err:
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx = MagicMock()
        mock_conn_ctx.__enter__ = lambda s: mock_conn_ctx
        mock_conn_ctx.__exit__ = MagicMock(return_value=False)
        mock_conn_ctx.cursor.return_value = mock_cursor
        mock_conn.return_value = mock_conn_ctx

        result = ingest_scraped_pages(dry_run=False, limit=10)

    mock_upsert.assert_called_once()
    mock_err.assert_not_called()
    # marking inline: cursor.execute chamado para SELECT (lookup id) + UPDATE scraped_pages
    assert mock_cursor.execute.call_count == 2
    calls_sql = [c[0][0] for c in mock_cursor.execute.call_args_list]
    assert any("SELECT id FROM articles" in s for s in calls_sql)
    assert any("ingestion_status" in s for s in calls_sql)
    assert result["inserted"] == 1
    assert result["errors"] == 0


def test_ingest_real_chama_mark_error_em_falha():
    """Quando upsert_article lança exceção, mark_scraped_page_ingestion_error é chamado."""
    from news_radar.scraper.ingestion import ingest_scraped_pages
    page = _make_page()

    with patch("news_radar.scraper.ingestion.get_eligible_pages", return_value=[page]), \
         patch("news_radar.scraper.ingestion.connect") as mock_conn, \
         patch("news_radar.scraper.ingestion.upsert_article", side_effect=RuntimeError("db fail")), \
         patch("news_radar.scraper.ingestion.mark_scraped_page_ingested") as mock_mark, \
         patch("news_radar.scraper.ingestion.mark_scraped_page_ingestion_error") as mock_err:
        mock_conn_ctx = MagicMock()
        mock_conn_ctx.__enter__ = lambda s: mock_conn_ctx
        mock_conn_ctx.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_conn_ctx

        result = ingest_scraped_pages(dry_run=False, limit=10)

    mock_mark.assert_not_called()
    mock_err.assert_called_once()
    assert result["errors"] == 1


# ══════════════════════════════════════════════════════════════════════════════
# 5. count_eligible_pages e get_eligible_pages — fallback sem banco
# ══════════════════════════════════════════════════════════════════════════════

def test_count_eligible_pages_sem_banco():
    """count_eligible_pages retorna 0 sem banco disponível."""
    from news_radar.scraper.ingestion import count_eligible_pages
    with patch("news_radar.scraper.ingestion.connect", side_effect=Exception("no db")):
        assert count_eligible_pages() == 0


def test_get_eligible_pages_sem_banco():
    """get_eligible_pages retorna lista vazia sem banco."""
    from news_radar.scraper.ingestion import get_eligible_pages
    with patch("news_radar.scraper.ingestion.connect", side_effect=Exception("no db")):
        assert get_eligible_pages() == []


# ══════════════════════════════════════════════════════════════════════════════
# 6. insert_scraped_page aceita content_text
# ══════════════════════════════════════════════════════════════════════════════

def test_insert_scraped_page_aceita_content_text():
    """insert_scraped_page deve aceitar parâmetro content_text sem erro."""
    from news_radar.scraper.runs import insert_scraped_page
    import inspect
    sig = inspect.signature(insert_scraped_page)
    assert "content_text" in sig.parameters, "insert_scraped_page não tem parâmetro content_text"


def test_insert_scraped_page_content_text_default_none():
    """content_text deve ter default None (backward-compatible)."""
    from news_radar.scraper.runs import insert_scraped_page
    import inspect
    sig = inspect.signature(insert_scraped_page)
    param = sig.parameters.get("content_text")
    assert param is not None
    assert param.default is None


# ══════════════════════════════════════════════════════════════════════════════
# 7. CLI — ingest-scraping existe e aceita argumentos
# ══════════════════════════════════════════════════════════════════════════════

def test_cli_ingest_scraping_existe():
    """Comando ingest-scraping deve estar registrado no parser."""
    from news_radar.cli import build_parser
    parser = build_parser()
    subparsers_actions = [a for a in parser._actions
                          if hasattr(a, "_name_parser_map")]
    assert subparsers_actions, "Nenhum subparser encontrado"
    subparser_map = subparsers_actions[0]._name_parser_map
    assert "ingest-scraping" in subparser_map, "Comando ingest-scraping não registrado"


def test_cli_ingest_scraping_dry_run_flag():
    """ingest-scraping deve aceitar --dry-run sem erro."""
    from news_radar.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["ingest-scraping", "--dry-run", "--limit", "5"])
    assert args.dry_run is True
    assert args.limit == 5


def test_cli_ingest_scraping_default_limit():
    """Limite padrão deve ser 50."""
    from news_radar.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["ingest-scraping"])
    assert args.limit == 50
    assert args.dry_run is False


def test_cli_ingest_scraping_source_name():
    """--source-name deve ser aceito."""
    from news_radar.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["ingest-scraping", "--source-name", "G1 Piauí"])
    assert args.source_name == "G1 Piauí"


def test_cli_ingest_scraping_run_id():
    """--run-id deve ser aceito."""
    from news_radar.cli import build_parser
    parser = build_parser()
    args = parser.parse_args(["ingest-scraping", "--run-id", "123"])
    assert args.run_id == 123


# ══════════════════════════════════════════════════════════════════════════════
# 8. Dashboard queries — fallback sem banco
# ══════════════════════════════════════════════════════════════════════════════

def test_ingestion_overview_sem_banco():
    """ingestion_overview retorna dict com zeros sem banco."""
    from news_radar.dashboard_queries import ingestion_overview
    with patch("news_radar.dashboard_queries.connect", side_effect=Exception("no db")):
        ov = ingestion_overview()
    assert isinstance(ov, dict)
    assert ov.get("pages_total", 0) == 0
    assert ov.get("pages_pending", 0) == 0
    assert ov.get("pages_ingested", 0) == 0


def test_ingestion_recent_results_sem_banco():
    """ingestion_recent_results retorna lista vazia sem banco."""
    from news_radar.dashboard_queries import ingestion_recent_results
    with patch("news_radar.dashboard_queries.connect", side_effect=Exception("no db")):
        results = ingestion_recent_results()
    assert results == []


# ══════════════════════════════════════════════════════════════════════════════
# 9. Compatibilidade — RSS continua funcionando
# ══════════════════════════════════════════════════════════════════════════════

def test_collector_nao_foi_alterado():
    """collector.py ainda exporta as funções essenciais."""
    from news_radar import collector
    assert hasattr(collector, "collect_feeds")
    assert hasattr(collector, "upsert_article")
    assert hasattr(collector, "normalize_entry")


def test_ranker_nao_foi_alterado():
    """ranker.py ainda exporta automatic_scores e rank_all."""
    from news_radar import ranker
    assert hasattr(ranker, "automatic_scores")
    assert hasattr(ranker, "rank_all")
    assert hasattr(ranker, "combine_with_ai")


# ══════════════════════════════════════════════════════════════════════════════
# 10. scraper/__init__ exporta funções de ingestion
# ══════════════════════════════════════════════════════════════════════════════

def test_scraper_init_exporta_ingestion():
    """scraper/__init__.py deve exportar funções de ingestion."""
    from news_radar.scraper import (
        ingest_scraped_pages,
        build_article_from_scraped_page,
        get_eligible_pages,
        count_eligible_pages,
        mark_scraped_page_ingested,
        mark_scraped_page_ingestion_error,
    )
    assert callable(ingest_scraped_pages)
    assert callable(build_article_from_scraped_page)
    assert callable(get_eligible_pages)
    assert callable(count_eligible_pages)
    assert callable(mark_scraped_page_ingested)
    assert callable(mark_scraped_page_ingestion_error)


# ══════════════════════════════════════════════════════════════════════════════
# 11. Testes com banco real (opcionais)
# ══════════════════════════════════════════════════════════════════════════════

@requires_db
def test_db_migration_v10_2_applied():
    """Com banco real, confirma que as migrations v10.2 foram aplicadas."""
    from news_radar.db import init_db, connect
    init_db()
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'scraped_pages'
                  AND column_name IN (
                    'ingestion_status', 'article_id',
                    'ingestion_error', 'ingested_at', 'content_text'
                  )
            """)
            cols = {r["column_name"] for r in cur.fetchall()}
    expected = {"ingestion_status", "article_id", "ingestion_error", "ingested_at", "content_text"}
    assert expected <= cols, f"Colunas ausentes: {expected - cols}"
