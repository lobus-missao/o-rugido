"""Migration: cria tabela dispatches para controle editorial por edição."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from news_radar.db import connect

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dispatches (
                id                      SERIAL PRIMARY KEY,
                article_id              TEXT NOT NULL,
                edition                 TEXT NOT NULL,  -- morning | noon | evening
                edition_date            DATE NOT NULL,
                rank                    INTEGER NOT NULL, -- 1, 2, 3
                scope                   TEXT NOT NULL DEFAULT 'brasil',
                status                  TEXT NOT NULL DEFAULT 'pending_article',
                -- pending_article: enviado pro TG, aguardando aprovação
                -- article_approved: artigo aprovado, card a gerar
                -- article_rejected: artigo rejeitado
                -- pending_card: card enviado pro TG, aguardando aprovação
                -- card_approved: card aprovado, pronto para publicar
                -- card_rejected: card rejeitado (pode regerar)
                -- published: publicado
                article_tg_message_id   TEXT,
                card_tg_message_id      TEXT,
                card_path               TEXT,
                notes                   TEXT,
                created_at              TIMESTAMPTZ DEFAULT NOW(),
                updated_at              TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_dispatches_edition
            ON dispatches(edition_date, edition)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_dispatches_status
            ON dispatches(status)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_dispatches_article
            ON dispatches(article_id)
        """)
        cur.execute("SELECT COUNT(*) n FROM dispatches")
        print(f"Tabela dispatches criada. Registros: {cur.fetchone()['n']}")

print("Migração concluída.")
