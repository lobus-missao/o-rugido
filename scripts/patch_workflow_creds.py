"""
Vincula a credencial Telegram nos nós do workflow n8n diretamente no SQLite.
"""
import sqlite3, json
from datetime import datetime, timezone

CRED_ID = "d02309d63d0c4d56"
CRED_NAME = "News Radar Telegram Bot"
WORKFLOW_ID = "wP740vEMvW5QsJwQ"
DB = r"C:\Users\robep\.n8n\database.sqlite"

TELEGRAM_TYPES = {"n8n-nodes-base.telegram", "n8n-nodes-base.telegramTrigger"}

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

row = conn.execute("SELECT * FROM workflow_entity WHERE id = ?", (WORKFLOW_ID,)).fetchone()
if not row:
    print("Workflow nao encontrado!")
    conn.close()
    exit(1)

wf_data = dict(row)

# Parse do JSON de nodes
nodes = json.loads(wf_data["nodes"])
updated = 0

for node in nodes:
    if node.get("type") in TELEGRAM_TYPES:
        node["credentials"] = {
            "telegramApi": {
                "id": CRED_ID,
                "name": CRED_NAME
            }
        }
        print(f"  Vinculado: {node.get('name')} [{node.get('type')}]")
        updated += 1

if updated == 0:
    print("Nenhum no Telegram encontrado!")
    conn.close()
    exit(1)

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000")

conn.execute(
    "UPDATE workflow_entity SET nodes = ?, updatedAt = ? WHERE id = ?",
    (json.dumps(nodes), now, WORKFLOW_ID)
)

# Atualiza tambem o workflow_published_version se existir
pub = conn.execute(
    "SELECT * FROM workflow_published_version WHERE workflowId = ?",
    (WORKFLOW_ID,)
).fetchone()

if pub:
    pub_data = json.loads(pub["nodes"])
    for node in pub_data:
        if node.get("type") in TELEGRAM_TYPES:
            node["credentials"] = {
                "telegramApi": {"id": CRED_ID, "name": CRED_NAME}
            }
    conn.execute(
        "UPDATE workflow_published_version SET nodes = ?, updatedAt = ? WHERE workflowId = ?",
        (json.dumps(pub_data), now, WORKFLOW_ID)
    )
    print("  Versao publicada atualizada tambem")

conn.commit()
conn.close()

print(f"\n{updated} nos atualizados com a credencial Telegram.")
print("Reinicie o n8n para aplicar as mudancas (Ctrl+C no terminal do n8n e npx n8n novamente).")
