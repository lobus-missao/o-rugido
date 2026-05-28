"""
Corrige o workflow do n8n:
1. Nó de notificação roda apenas UMA vez (executeOnce)
2. Timeout do collect aumentado para suportar 57 feeds
"""
import sqlite3, json
from datetime import datetime, timezone

DB = r"C:\Users\robep\.n8n\database.sqlite"
WORKFLOW_ID = "wP740vEMvW5QsJwQ"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

row = conn.execute("SELECT nodes FROM workflow_entity WHERE id=?", (WORKFLOW_ID,)).fetchone()
nodes = json.loads(row["nodes"])

for node in nodes:
    name = node.get("name", "")

    # Notificação: executeOnce = True para não mandar 3x
    if name == "4. Notificar lotes prontos":
        node["executeOnce"] = True
        print(f"Fix executeOnce: {name}")

    # Collect: timeout maior
    if name == "1. Coletar feeds" and node.get("type") == "n8n-nodes-base.code":
        js = node.get("parameters", {}).get("jsCode", "")
        js = js.replace("timeout: 120000", "timeout: 200000")
        node["parameters"]["jsCode"] = js
        print(f"Fix timeout: {name}")

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000")
conn.execute("UPDATE workflow_entity SET nodes=?, updatedAt=? WHERE id=?",
             (json.dumps(nodes), now, WORKFLOW_ID))
conn.commit()
conn.close()
print("Workflow corrigido.")
