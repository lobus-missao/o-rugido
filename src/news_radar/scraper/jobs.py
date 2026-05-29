"""Orquestra testes de URL e scraping de fonte."""
from __future__ import annotations
import hashlib
import time
import traceback
from typing import Any

from .models import ExtractionResult, ScrapeRunStats
from .registry import run_strategy
from .runs import create_scrape_run, finish_scrape_run, insert_scraped_page


def run_extraction_test(
    url: str,
    strategy: str = "trafilatura",
    config: dict[str, Any] | None = None,
    timeout: int = 30,
) -> ExtractionResult:
    """
    Testa a extração de uma URL sem salvar artigo no banco.
    Seguro para uso no dashboard e CLI.
    """
    result = run_strategy(strategy=strategy, url=url, config=config, timeout=timeout)
    return result


def run_source_scrape(
    source_id: int | None,
    strategy: str,
    urls: list[str],
    config: dict[str, Any] | None = None,
    timeout: int = 30,
    rate_limit: float = 2.0,
    dry_run: bool = False,
    max_items: int = 50,
) -> dict[str, Any]:
    """
    Executa scraping de uma lista de URLs para uma fonte.

    dry_run=True: roda extração mas não persiste artigos.
    Registra scrape_run no banco (mesmo em dry_run).
    """
    run_id = None
    stats = ScrapeRunStats()
    results: list[dict] = []

    try:
        run_id = create_scrape_run(source_id, strategy)
        urls_to_process = urls[:max_items]
        stats.found = len(urls_to_process)

        for url in urls_to_process:
            time.sleep(rate_limit)
            try:
                extraction = run_strategy(
                    strategy=strategy,
                    url=url,
                    config=config,
                    timeout=timeout,
                    rate_limit=0,  # rate_limit já aplicado no loop
                )

                content_hash = None
                if extraction.content:
                    content_hash = hashlib.sha256(extraction.content.encode()).hexdigest()[:16]

                status = "ok" if extraction.ok else "error"

                if not dry_run:
                    insert_scraped_page(
                        source_id=source_id,
                        run_id=run_id,
                        url=url,
                        status_code=None,
                        content_hash=content_hash,
                        extraction_status=status,
                        title=extraction.title,
                        error_message=extraction.error,
                    )

                if extraction.ok:
                    stats.inserted += 1
                else:
                    stats.errors += 1

                results.append({
                    "url": url,
                    "ok": extraction.ok,
                    "title": extraction.title,
                    "quality": extraction.extraction_quality,
                    "error": extraction.error,
                })

            except Exception as exc:
                stats.errors += 1
                err = f"{str(exc)[:200]}\n{traceback.format_exc(limit=1)}"
                results.append({"url": url, "ok": False, "error": err})

    except Exception as exc:
        stats.error_message = str(exc)[:500]

    finally:
        if run_id:
            finish_scrape_run(run_id, stats, metadata={"dry_run": dry_run, "urls_count": len(urls)})

    return {
        "run_id": run_id,
        "dry_run": dry_run,
        "strategy": strategy,
        "stats": {
            "found": stats.found,
            "inserted": stats.inserted,
            "errors": stats.errors,
        },
        "results": results,
    }
