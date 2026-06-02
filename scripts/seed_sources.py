#!/usr/bin/env python3
"""
Seed script — Fase 2.
Importa feeds de configs/feeds.yaml para a tabela sources.

Idempotente: usa upsert por name. Seguro para rodar múltiplas vezes.
Não altera o comportamento atual de coleta (feeds.yaml continua como fallback).

Uso:
    python scripts/seed_sources.py
    python scripts/seed_sources.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from news_radar.services.feeds import load_feeds_config
from news_radar.core.db import init_db
from news_radar.repositories.sources import upsert_source


def seed_sources(dry_run: bool = False) -> dict:
    """Lê feeds.yaml e faz upsert de cada entrada na tabela sources.

    Retorna dict com contagens: total, processed, skipped.
    """
    config = load_feeds_config()
    feeds = config.get("feeds", [])

    processed = 0
    skipped = 0

    for feed in feeds:
        name = (feed.get("name") or "").strip()
        url = (feed.get("url") or "").strip()
        if not name or not url:
            skipped += 1
            continue

        if dry_run:
            print(f"  [dry-run] upsert: {name!r} ({feed.get('scope','brasil')}) {url}")
            processed += 1
            continue

        upsert_source(
            name=name,
            url=url,
            source_type="rss",
            scope=feed.get("scope", "piaui"),
            trust=float(feed.get("trust", 0.5)),
            enabled=bool(feed.get("enabled", True)),
        )
        processed += 1

    return {"total": len(feeds), "processed": processed, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed sources from feeds.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Mostra o que seria feito sem alterar o banco")
    args = parser.parse_args()

    if not args.dry_run:
        print("Inicializando banco...")
        init_db()

    print(f"{'[DRY-RUN] ' if args.dry_run else ''}Importando feeds.yaml para tabela sources...")
    result = seed_sources(dry_run=args.dry_run)
    print(
        f"Concluído: {result['processed']} processados"
        f", {result['skipped']} ignorados"
        f" (total no yaml: {result['total']})"
    )


if __name__ == "__main__":
    main()
