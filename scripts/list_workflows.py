import sqlite3
conn = sqlite3.connect(r"C:\Users\robep\.n8n\database.sqlite")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, name, active FROM workflow_entity ORDER BY createdAt DESC LIMIT 10").fetchall()
for r in rows:
    status = "ATIVO  " if r["active"] else "inativo"
    print(f"  [{status}] {r['name'][:55]}")
    print(f"           ID: {r['id']}")
conn.close()
