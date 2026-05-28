import sqlite3
from datetime import datetime, timezone

conn = sqlite3.connect(r"C:\Users\robep\.n8n\database.sqlite")
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000")
old_ids = ("eHClcWOBzwQp1wrM", "t1ze1KmvdxT9LQSU")
for wid in old_ids:
    conn.execute("UPDATE workflow_entity SET isArchived=1, updatedAt=? WHERE id=?", (now, wid))
    print(f"Arquivado: {wid}")
conn.commit()
conn.close()
