"""
Ativa o workflow n8n diretamente no banco SQLite.
O n8n precisa ser reiniciado depois para registrar o scheduler.
"""
import sqlite3, json
from datetime import datetime, timezone

DB = r"C:\Users\robep\.n8n\database.sqlite"
WORKFLOW_ID = "wP740vEMvW5QsJwQ"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000")

# Verifica estado atual
row = conn.execute("SELECT id, active FROM workflow_entity WHERE id = ?", (WORKFLOW_ID,)).fetchone()
if not row:
    print("Workflow nao encontrado!")
    conn.close()
    exit(1)

print(f"Estado atual: active={row['active']}")

# Ativa o workflow
conn.execute("UPDATE workflow_entity SET active = 1, updatedAt = ? WHERE id = ?", (now, WORKFLOW_ID))

# Atualiza versao publicada se existir
pub = conn.execute("SELECT * FROM workflow_published_version WHERE workflowId = ?", (WORKFLOW_ID,)).fetchone()
if pub:
    conn.execute("UPDATE workflow_published_version SET updatedAt = ? WHERE workflowId = ?", (now, WORKFLOW_ID))
    print("Versao publicada atualizada.")

conn.commit()
conn.close()

print(f"Workflow {WORKFLOW_ID} ativado!")
print("Reinicie o n8n (npx n8n) para que o scheduler comece a disparar.")
