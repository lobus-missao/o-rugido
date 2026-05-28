"""
Adiciona timeout longo + retry nos nodes HTTP Request do workflow n8n.
Executar sempre que o workflow for recriado.
"""
import sqlite3, json
from datetime import datetime, timezone

DB = r"C:\Users\robep\.n8n\database.sqlite"
WORKFLOW_ID = "wP740vEMvW5QsJwQ"

# Timeouts por tipo de operacao (ms)
TIMEOUTS = {
    "1. Coletar feeds": 120000,   # collect pode demorar ~60s com 57 feeds
    "2. Calcular ranking": 60000,
    "3a. Lotes Brasil": 30000,
    "3b. Lotes Piaui": 30000,
    "3c. Lotes Teresina": 30000,
    "4. Checar lotes pendentes": 10000,
    "6. Limpeza": 30000,
    "Atualizar status banco": 10000,
}

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

row = conn.execute("SELECT nodes FROM workflow_entity WHERE id = ?", (WORKFLOW_ID,)).fetchone()
if not row:
    print("Workflow nao encontrado!")
    conn.close()
    exit(1)

nodes = json.loads(row["nodes"])
updated = 0

for node in nodes:
    name = node.get("name", "")
    if node.get("type") == "n8n-nodes-base.httpRequest":
        timeout_ms = TIMEOUTS.get(name, 60000)
        params = node.setdefault("parameters", {})
        opts = params.setdefault("options", {})
        opts["timeout"] = timeout_ms

        # Retry on fail
        node["retryOnFail"] = True
        node["maxTries"] = 2
        node["waitBetweenTries"] = 3000

        print(f"  {name}: timeout={timeout_ms}ms, retry=2x")
        updated += 1

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000")
conn.execute("UPDATE workflow_entity SET nodes = ?, updatedAt = ? WHERE id = ?",
             (json.dumps(nodes), now, WORKFLOW_ID))
conn.commit()
conn.close()

print(f"\n{updated} nodes atualizados.")
