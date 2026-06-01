from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .repositories.articles import SCORE_COLUMN, stats, top_articles, update_card_status
from .services.ingestion import collect_feeds
from .services.ranker import rank_all
from .core.config import DATABASE_URL
from .core.db import connect, init_db


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


# ── Comandos ─────────────────────────────────────────────────────────────────

def cmd_init_db(args) -> None:
    init_db()
    print("Banco inicializado.")


def cmd_collect(args) -> None:
    result = collect_feeds(limit_per_feed=args.limit_per_feed)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))


def cmd_rank(args) -> None:
    count = rank_all()
    print(f"Ranking recalculado: {count} artigos.")


def cmd_show(args) -> None:
    items = top_articles(scope=args.scope, limit=args.limit)
    column = SCORE_COLUMN[args.scope]
    if not items:
        print("Nenhum artigo. Rode collect + rank.")
        return
    for idx, item in enumerate(items, start=1):
        score = item[column]
        published = item["published_at"] or "sem data"
        url = item["canonical_url"] or item["url"]
        print(f"\n#{idx} | score={score:.1f} | {item['source']} | {published}")
        print(item["title"])
        print(url)


def cmd_make_card(args) -> None:
    from .services.rendering import render_cards

    generated = render_cards(scope=args.scope, limit=args.limit)
    if not generated:
        print("Nenhum artigo pendente de card.")
        return
    for item in generated:
        print(f"- {item['article_id']} | {item['title'][:60]}")
        print(f"  card={item['card_path']}")


def cmd_update_card_status(args) -> None:
    update_card_status(args.article_id, status=args.status)
    print(json.dumps({"article_id": args.article_id, "status": args.status}, ensure_ascii=False))


def cmd_dispatch(args) -> None:
    from .services.editorial import EDITIONS, create_dispatch

    edition = args.edition
    if edition not in EDITIONS:
        print(json.dumps(
            {"ok": False, "error": f"edition inválida. Use: {list(EDITIONS.keys())}"},
            ensure_ascii=False,
        ))
        return
    created = create_dispatch(edition=edition, scope=args.scope, top=args.top, dry_run=args.dry_run)
    print(json.dumps({
        "ok": True,
        "edition": edition,
        "scope": args.scope,
        "dry_run": args.dry_run,
        "dispatched": len(created),
        "dispatch_ids": [c["dispatch_id"] for c in created],
    }, ensure_ascii=False, default=_json_default))


def cmd_mark_published(args) -> None:
    from .services.editorial import mark_published

    mark_published(args.dispatch_id)
    print(json.dumps(
        {"ok": True, "dispatch_id": args.dispatch_id, "status": "published"},
        ensure_ascii=False,
    ))


def cmd_cleanup(args) -> None:
    cutoff_articles = datetime.now(timezone.utc) - timedelta(days=args.days)
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM articles
                WHERE published_at < %s
                  AND card_status NOT IN ('approved')
                  AND ai_score IS NULL
                """,
                (cutoff_articles,),
            )
            deleted_articles = cur.rowcount
    print(json.dumps({
        "deleted_articles": deleted_articles,
        "articles_older_than_days": args.days,
    }, ensure_ascii=False, indent=2))


def cmd_backup(args) -> None:
    """Exporta o banco via pg_dump."""
    output = args.output or f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        print(json.dumps({
            "ok": False,
            "error": "pg_dump não encontrado. Instale postgresql-client ou use Docker.",
            "manual": f"docker exec <container_postgres> pg_dump -U <user> news_radar > {output}",
        }, ensure_ascii=False))
        return

    result = subprocess.run(
        [pg_dump, DATABASE_URL, "--no-password"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode == 0:
        Path(output).write_text(result.stdout, encoding="utf-8")
        print(json.dumps({
            "ok": True,
            "file": str(Path(output).resolve()),
            "size_bytes": Path(output).stat().st_size,
        }, ensure_ascii=False))
    else:
        print(json.dumps({
            "ok": False,
            "error": result.stderr.strip()[:300] or "pg_dump falhou sem mensagem",
        }, ensure_ascii=False))


def cmd_stats(args) -> None:
    print(json.dumps(stats(), ensure_ascii=False, indent=2, default=_json_default))


# ── Parser ───────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="news-radar", description="News Radar — CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="Aplica migrations pendentes.").set_defaults(func=cmd_init_db)

    p = sub.add_parser("collect", help="Coleta RSS das fontes em configs/feeds.yaml.")
    p.add_argument("--limit-per-feed", type=int, default=30)
    p.set_defaults(func=cmd_collect)

    sub.add_parser("rank", help="Recalcula scores automáticos.").set_defaults(func=cmd_rank)

    p = sub.add_parser("show", help="Lista top artigos por score.")
    p.add_argument("--scope", default="piaui", choices=["piaui"])
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("make-card", help="Gera PNG dos artigos pendentes.")
    p.add_argument("--scope", default="piaui", choices=["piaui"])
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_make_card)

    p = sub.add_parser("update-card-status", help="Atualiza card_status de um artigo.")
    p.add_argument("--article-id", required=True)
    p.add_argument("--status", required=True)
    p.set_defaults(func=cmd_update_card_status)

    p = sub.add_parser("dispatch", help="Cria um dispatch (envio editorial).")
    p.add_argument("--edition", default="default")
    p.add_argument("--scope", default="piaui", choices=["piaui"])
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_dispatch)

    p = sub.add_parser("mark-published", help="Marca um dispatch como publicado.")
    p.add_argument("--dispatch-id", type=int, required=True)
    p.set_defaults(func=cmd_mark_published)

    p = sub.add_parser("cleanup", help="Remove artigos antigos sem score/aprovação.")
    p.add_argument("--days", type=int, default=30)
    p.set_defaults(func=cmd_cleanup)

    p = sub.add_parser("backup", help="Exporta o banco via pg_dump.")
    p.add_argument("--output", help="Arquivo de saída (default: backup_YYYYMMDD_HHMMSS.sql)")
    p.set_defaults(func=cmd_backup)

    sub.add_parser("stats", help="Estatísticas do banco.").set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
