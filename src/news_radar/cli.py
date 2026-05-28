from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import psycopg2.extras

from .ai_batches import (
    get_ai_batch,
    import_ai_result,
    list_ai_batches,
    make_ai_batches,
)
from .collector import collect_feeds
from .config import OLLAMA_MODEL
from .db import connect, init_db, json_dumps
from .ranker import automatic_scores, combine_with_ai
from .repository import SCORE_COLUMN, stats, top_articles, update_card_status


def cmd_init_db(args) -> None:
    init_db()
    print("Banco inicializado com sucesso.")


def cmd_collect(args) -> None:
    result = collect_feeds(limit_per_feed=args.limit_per_feed)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))


def cmd_rank(args) -> None:
    init_db()

    # Calcula scores em memória antes de abrir qualquer transação
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, summary, source_scope, source_trust, published_at, ai_score FROM articles")
            rows = [dict(r) for r in cur.fetchall()]

    batch = []
    for article in rows:
        scores = automatic_scores(article)
        ai_score = float(article["ai_score"]) if article["ai_score"] is not None else None
        batch.append((
            scores["auto_score_brasil"],
            scores["auto_score_piaui"],
            scores["auto_score_teresina"],
            combine_with_ai(scores["auto_score_brasil"], ai_score),
            combine_with_ai(scores["auto_score_piaui"], ai_score),
            combine_with_ai(scores["auto_score_teresina"], ai_score),
            json_dumps(scores.get("reasons", [])),
            article["id"],
        ))

    # Atualiza tudo em uma única transação rápida
    with connect() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                """
                UPDATE articles SET
                    auto_score_brasil = %s,
                    auto_score_piaui = %s,
                    auto_score_teresina = %s,
                    final_score_brasil = %s,
                    final_score_piaui = %s,
                    final_score_teresina = %s,
                    score_reasons_json = %s
                WHERE id = %s
                """,
                batch,
                page_size=100,
            )

    print(f"Ranking recalculado para {len(batch)} noticias.")


def cmd_show(args) -> None:
    items = top_articles(scope=args.scope, limit=args.limit)
    column = SCORE_COLUMN[args.scope]

    if not items:
        print("Nenhuma noticia encontrada. Rode collect e rank primeiro.")
        return

    for idx, item in enumerate(items, start=1):
        score = item[column]
        published = item["published_at"] or "sem data"
        priority = item["priority"] or "-"
        category = item["category"] or "-"
        url = item["canonical_url"] or item["url"]
        print(f"\n#{idx} | score={score:.1f} | {item['source']} | {published}")
        print(item["title"])
        print(f"categoria={category} | prioridade={priority}")
        print(url)


def cmd_make_ai_batches(args) -> None:
    days = None if args.days_back == 0 else args.days_back
    generated = make_ai_batches(
        scope=args.scope,
        top=args.top,
        batch_size=args.batch_size,
        days_back=days,
    )
    if not generated:
        print("Nenhum lote gerado. Rode collect e rank primeiro.")
        return

    print("Lotes gerados:")
    for item in generated:
        print(
            f"- {item['batch_id']} | {item['prompt']} ({item['items']} noticias) "
            f"| ~{item['estimated_tokens']} tokens"
        )


def cmd_list_ai_batches(args) -> None:
    batches = list_ai_batches(limit=args.limit, status=args.status)
    if not batches:
        print("Nenhum lote encontrado.")
        return

    for batch in batches:
        print(
            f"{batch['batch_id']} | scope={batch['scope']} | status={batch['status']} "
            f"| itens={batch['article_count']} | model={batch['model'] or '-'}"
        )
        if batch["result_path"]:
            print(f"  resultado={batch['result_path']}")
        if batch["error"]:
            print(f"  erro={batch['error']}")


def cmd_send_ai_batch(args) -> None:
    from .ai_caller import send_ai_batch
    result = send_ai_batch(args.batch_id, model=args.model, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))


def cmd_import_ai(args) -> None:
    batch_id = args.batch_id
    if not batch_id:
        path = Path(args.file)
        batch_name = path.name.removesuffix(".json").removesuffix(".result")
        batch = get_ai_batch(batch_name)
        if batch:
            batch_id = batch["batch_id"]
    result = import_ai_result(args.file, batch_id=batch_id)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))


def cmd_make_card(args) -> None:
    from .card_renderer import render_cards
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


def cmd_send_card_telegram(args) -> None:
    from .telegram_sender import send_card_for_approval
    from .card_renderer import render_cards

    # Gera o card se ainda não existe
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM articles WHERE id = %s", (args.article_id,))
            row = cur.fetchone()

    if not row:
        print(json.dumps({"error": f"Artigo nao encontrado: {args.article_id}"}))
        return

    article = dict(row)
    card_path = article.get("card_path")

    if not card_path or not Path(card_path).exists():
        cards = render_cards(scope=article.get("source_scope", "brasil"), limit=1)
        if not cards:
            print(json.dumps({"error": "Nao foi possivel gerar o card"}))
            return
        card_path = cards[0]["card_path"]

    result = send_card_for_approval(article, card_path)
    update_card_status(args.article_id, status="pending")
    print(json.dumps({"sent": True, "message_id": result.get("result", {}).get("message_id")}, ensure_ascii=False))


def cmd_telegram_webhook(args) -> None:
    from .telegram_sender import set_webhook, delete_webhook, get_webhook_info
    if args.action == "set":
        url = args.url or os.getenv("TELEGRAM_WEBHOOK_URL", "")
        if not url:
            print("Informe --url ou defina TELEGRAM_WEBHOOK_URL no .env")
            return
        result = set_webhook(url)
    elif args.action == "delete":
        result = delete_webhook()
    else:
        result = get_webhook_info()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))


def cmd_dispatch(args) -> None:
    from .dispatch import create_dispatch, EDITIONS
    edition = args.edition
    if edition not in EDITIONS:
        print(json.dumps({"ok": False, "error": f"edition deve ser: {list(EDITIONS.keys())}"},
                         ensure_ascii=False, default=_json_default))
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
    from .dispatch import mark_published
    mark_published(args.dispatch_id)
    print(json.dumps({"ok": True, "dispatch_id": args.dispatch_id, "status": "published"},
                     ensure_ascii=False, default=_json_default))


def cmd_cleanup(args) -> None:
    from datetime import datetime, timedelta, timezone
    cutoff_articles = datetime.now(timezone.utc) - timedelta(days=args.days)
    cutoff_batches = datetime.now(timezone.utc) - timedelta(hours=args.expire_batches_hours)

    with connect() as conn:
        with conn.cursor() as cur:
            # Remove artigos velhos sem score de IA e sem card aprovado
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

            # Expira lotes pending antigos
            cur.execute(
                """
                UPDATE ai_batches
                SET status = 'expired', updated_at = NOW()
                WHERE status = 'pending'
                  AND created_at < %s
                """,
                (cutoff_batches,),
            )
            expired_batches = cur.rowcount

    print(json.dumps({
        "deleted_articles": deleted_articles,
        "expired_batches": expired_batches,
        "articles_older_than_days": args.days,
        "batches_older_than_hours": args.expire_batches_hours,
    }, ensure_ascii=False, indent=2))


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


def cmd_stats(args) -> None:
    print(json.dumps(stats(), ensure_ascii=False, indent=2, default=_json_default))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="news-radar",
        description="Monitoramento RSS com ranking Brasil, Piaui, Teresina e pipeline de IA local.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db", help="Cria ou atualiza o banco PostgreSQL.")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("collect", help="Coleta noticias dos feeds RSS.")
    p.add_argument("--limit-per-feed", type=int, default=30)
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("rank", help="Recalcula ranking automatico e final.")
    p.set_defaults(func=cmd_rank)

    p = sub.add_parser("show", help="Mostra ranking no terminal.")
    p.add_argument("--scope", choices=["brasil", "piaui", "teresina"], default="brasil")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("make-ai-batches", help="Gera lotes para envio ao Ollama.")
    p.add_argument("--scope", choices=["brasil", "piaui", "teresina"], default="brasil")
    p.add_argument("--top", type=int, default=200)
    p.add_argument("--batch-size", type=int, default=100)
    p.add_argument("--days-back", type=int, default=3, help="Somente artigos dos ultimos N dias (0=todos)")
    p.set_defaults(func=cmd_make_ai_batches)

    p = sub.add_parser("list-ai-batches", help="Lista os lotes de IA e seus status.")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--status", choices=["pending", "running", "completed", "failed"])
    p.set_defaults(func=cmd_list_ai_batches)

    p = sub.add_parser("send-ai-batch", help="Envia lote para o Ollama e importa resultado.")
    p.add_argument("--batch-id", required=True)
    p.add_argument("--model", default=OLLAMA_MODEL)
    p.add_argument("--timeout", type=int, default=300)
    p.set_defaults(func=cmd_send_ai_batch)

    p = sub.add_parser("import-ai", help="Importa JSON devolvido pela IA manualmente.")
    p.add_argument("--file", required=True)
    p.add_argument("--batch-id")
    p.set_defaults(func=cmd_import_ai)

    p = sub.add_parser("make-card", help="Gera cards PNG dos top artigos para aprovacao.")
    p.add_argument("--scope", choices=["brasil", "piaui", "teresina"], default="brasil")
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_make_card)

    p = sub.add_parser("update-card-status", help="Atualiza status do card apos aprovacao no Telegram.")
    p.add_argument("--article-id", required=True)
    p.add_argument("--status", choices=["approved", "rejected", "none"], required=True)
    p.set_defaults(func=cmd_update_card_status)

    p = sub.add_parser("send-card-telegram", help="Envia card de um artigo ao Telegram para aprovacao.")
    p.add_argument("--article-id", required=True)
    p.set_defaults(func=cmd_send_card_telegram)

    p = sub.add_parser("dispatch", help="Dispara top 3 artigos da edicao para aprovacao no Telegram.")
    p.add_argument("--edition", choices=["morning", "noon", "evening"], required=True)
    p.add_argument("--scope", choices=["brasil", "piaui", "teresina"], default="brasil")
    p.add_argument("--top", type=int, default=3)
    p.add_argument("--dry-run", action="store_true", help="Cria dispatches sem enviar mensagens reais ao Telegram.")
    p.set_defaults(func=cmd_dispatch)

    p = sub.add_parser("mark-published", help="Marca dispatch como publicado.")
    p.add_argument("--dispatch-id", type=int, required=True)
    p.set_defaults(func=cmd_mark_published)

    p = sub.add_parser("telegram-webhook", help="Configura o webhook do Telegram para o n8n.")
    p.add_argument("--action", choices=["set", "delete", "info"], default="info")
    p.add_argument("--url", help="URL do webhook n8n (necessario para --action set)")
    p.set_defaults(func=cmd_telegram_webhook)

    p = sub.add_parser("cleanup", help="Remove artigos velhos e expira lotes pendentes antigos.")
    p.add_argument("--days", type=int, default=30, help="Remove artigos sem IA mais velhos que N dias")
    p.add_argument("--expire-batches-hours", type=int, default=48, help="Expira lotes pending mais velhos que N horas")
    p.set_defaults(func=cmd_cleanup)

    p = sub.add_parser("stats", help="Mostra estatisticas do banco.")
    p.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
