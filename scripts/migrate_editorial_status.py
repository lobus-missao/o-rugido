"""Migration: adiciona editorial_status à tabela articles."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from news_radar.db import connect

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            ALTER TABLE articles
            ADD COLUMN IF NOT EXISTS editorial_status TEXT DEFAULT 'discovered'
        """)
        cur.execute("""
            UPDATE articles SET editorial_status =
              CASE
                WHEN card_status = 'approved'  THEN 'approved'
                WHEN card_status = 'rejected'  THEN 'rejected'
                WHEN card_status = 'pending'   THEN 'sent_to_telegram'
                WHEN ai_score IS NOT NULL AND priority IN ('alta','critica') THEN 'selected'
                WHEN ai_score IS NOT NULL      THEN 'ai_done'
                WHEN priority IN ('alta','critica') THEN 'needs_ai'
                ELSE 'discovered'
              END
            WHERE editorial_status = 'discovered' OR editorial_status IS NULL
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_editorial_status
            ON articles(editorial_status)
        """)
        cur.execute("""
            SELECT editorial_status, COUNT(*) n
            FROM articles GROUP BY editorial_status ORDER BY n DESC
        """)
        print("editorial_status distribuição:")
        for r in cur.fetchall():
            print(f"  {r['editorial_status']}: {r['n']}")

print("Migração concluída.")
