"""
Seed idempotente de portais candidatos do config/portal_sources_seed.yaml.

- Cria sources com enabled=False por padrão
- Cria source_rules com enabled=False por padrão
- Não duplica se source já existe (upsert por nome)
- Não ativa coleta automaticamente
- Compatível com --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from news_radar.db import connect, init_db


def _load_seed() -> list[dict]:
    seed_path = ROOT / "config" / "portal_sources_seed.yaml"
    if not seed_path.exists():
        print(f"ERRO: seed não encontrado em {seed_path}")
        sys.exit(1)
    with open(seed_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("portals", [])


def _upsert_source(cur, portal: dict) -> tuple[int, str]:
    """Insere ou atualiza source. Retorna (id, action)."""
    cur.execute("SELECT id, enabled FROM sources WHERE name = %s", (portal["name"],))
    existing = cur.fetchone()

    if existing:
        # Atualiza campos seguros sem alterar enabled
        cur.execute(
            """
            UPDATE sources SET
                url = %s,
                source_type = %s,
                scope = %s,
                trust = %s,
                updated_at = NOW()
            WHERE name = %s
            RETURNING id
            """,
            (
                portal["base_url"],
                portal.get("source_type", "portal"),
                portal["scope"],
                float(portal.get("trust", 3)) / 5.0,  # normaliza 1–5 para 0.0–1.0
                portal["name"],
            ),
        )
        return existing["id"], "updated"
    else:
        cur.execute(
            """
            INSERT INTO sources (name, url, source_type, scope, trust, enabled)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                portal["name"],
                portal["base_url"],
                portal.get("source_type", "portal"),
                portal["scope"],
                float(portal.get("trust", 3)) / 5.0,
                False,  # nunca ativar automaticamente
            ),
        )
        row = cur.fetchone()
        return row["id"], "inserted"


def _upsert_source_rule(cur, source_id: int, portal: dict) -> tuple[int, str]:
    """Insere ou atualiza source_rule para a fonte. Retorna (id, action)."""
    strategy = portal.get("strategy_suggested", "trafilatura")
    rss_url = portal.get("rss_url")
    cur.execute(
        "SELECT id, enabled FROM source_rules WHERE source_id = %s ORDER BY id LIMIT 1",
        (source_id,),
    )
    existing = cur.fetchone()

    if existing:
        return existing["id"], "skipped"
    else:
        cur.execute(
            """
            INSERT INTO source_rules (
                source_id, strategy, list_url, enabled,
                rate_limit_seconds, timeout_seconds
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                source_id,
                strategy,
                rss_url,
                False,  # nunca ativar automaticamente
                2.0,
                30,
            ),
        )
        row = cur.fetchone()
        return row["id"], "inserted"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed de portais candidatos")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem alterar banco")
    parser.add_argument("--init-db", action="store_true", help="Inicializa banco antes do seed")
    args = parser.parse_args()

    if args.init_db:
        print("Inicializando banco...")
        init_db()
        print("Banco inicializado.")

    portals = _load_seed()
    print(f"Seed carregado: {len(portals)} portais")

    if args.dry_run:
        print("[DRY RUN] Nenhuma alteração será feita no banco.\n")
        for p in portals:
            print(
                f"  {p['scope']:10} | {p['strategy_suggested']:15} | "
                f"trust={p.get('trust','?')} | {p['name']}"
            )
        print(f"\nTotal: {len(portals)} portais")
        return

    sources_inserted = sources_updated = 0
    rules_inserted = rules_skipped = 0

    with connect() as conn:
        with conn.cursor() as cur:
            for portal in portals:
                source_id, src_action = _upsert_source(cur, portal)
                if src_action == "inserted":
                    sources_inserted += 1
                else:
                    sources_updated += 1

                rule_id, rule_action = _upsert_source_rule(cur, source_id, portal)
                if rule_action == "inserted":
                    rules_inserted += 1
                else:
                    rules_skipped += 1

                needs = " [needs_validation]" if portal.get("needs_validation") else ""
                print(
                    f"  {src_action:8} source | {portal['scope']:10} | "
                    f"{portal.get('strategy_suggested','?'):15} | "
                    f"{portal['name']}{needs}"
                )

    print(
        f"\nSources: {sources_inserted} inseridas, {sources_updated} atualizadas"
        f"\nRules:   {rules_inserted} inseridas, {rules_skipped} já existiam"
        f"\nTodas com enabled=False — ativar manualmente após validação."
    )


if __name__ == "__main__":
    main()
