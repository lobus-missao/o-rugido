"""
Recria os 3 workflows de disparo editorial copiando o schema exato
do workflow que já funciona no n8n.
"""
import sqlite3, json, uuid
from datetime import datetime, timezone

DB = r"C:\Users\robep\.n8n\database.sqlite"
CRED_ID = "d02309d63d0c4d56"
CHAT_ID = "8773271293"
PYTHON = r"C:\Users\robep\Desktop\news_radar_rss\.venv\Scripts\python.exe"
CWD = r"C:\Users\robep\Desktop\news_radar_rss"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Pega o schema completo do workflow que funciona
ref = conn.execute(
    "SELECT * FROM workflow_entity WHERE id='wP740vEMvW5QsJwQ'"
).fetchone()
ref = dict(ref)

now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000")

DISPATCHES = [
    ("News Radar - Disparo Manha (6h30)",      6,  30, "morning"),
    ("News Radar - Disparo Meio-dia (11h30)", 11,  30, "noon"),
    ("News Radar - Disparo Tarde (17h30)",    17,  30, "evening"),
]

for name, hour, minute, edition in DISPATCHES:
    js = f"""const {{ execSync }} = require('child_process');
const PYTHON = {json.dumps(PYTHON)};
const CWD = {json.dumps(CWD)};
try {{
  const out = execSync(
    `"${{PYTHON}}" -m news_radar.cli dispatch --edition {edition} --scope brasil --top 3`,
    {{ cwd: CWD, timeout: 60000, encoding: 'utf8' }}
  );
  try {{ return [{{ json: JSON.parse(out) }}]; }}
  catch {{ return [{{ json: {{ ok: true, output: out.trim().slice(0, 200) }} }}]; }}
}} catch(e) {{
  return [{{ json: {{ ok: false, error: String(e.stderr || e.message || e).slice(0, 300) }} }}];
}}"""

    nodes = [
        {
            "id": "schedule-node",
            "name": f"Schedule {name}",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.3,
            "position": [0, 300],
            "parameters": {
                "rule": {
                    "interval": [{
                        "field": "cronExpression",
                        "expression": f"{minute} {hour} * * *",
                    }]
                }
            },
        },
        {
            "id": "dispatch-node",
            "name": "Executar Dispatch",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [240, 300],
            "parameters": {"mode": "runOnceForAllItems", "jsCode": js},
            "continueOnFail": True,
        },
        {
            "id": "notify-node",
            "name": "Notificar Telegram",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [480, 300],
            "credentials": {"telegramApi": {"id": CRED_ID, "name": "News Radar Telegram Bot"}},
            "parameters": {
                "resource": "message",
                "operation": "sendMessage",
                "chatId": CHAT_ID,
                "text": f"={{ $json.ok ? '*Disparo {name}* enviado! ' + $json.dispatched + ' artigo(s) no Telegram.' : '*Erro:* ' + $json.error }}",
                "additionalFields": {"parse_mode": "Markdown"},
            },
            "continueOnFail": True,
            "executeOnce": True,
        },
    ]

    connections = {
        f"Schedule {name}": {"main": [[{"node": "Executar Dispatch", "type": "main", "index": 0}]]},
        "Executar Dispatch": {"main": [[{"node": "Notificar Telegram", "type": "main", "index": 0}]]},
    }

    # Verifica se já existe
    existing = conn.execute("SELECT id FROM workflow_entity WHERE name=?", (name,)).fetchone()
    wf_id = existing["id"] if existing else uuid.uuid4().hex[:16]
    version_id = uuid.uuid4().hex

    if existing:
        conn.execute("""
            UPDATE workflow_entity SET nodes=?, connections=?, active=1,
            settings=?, staticData=?, versionId=?, updatedAt=? WHERE id=?
        """, (json.dumps(nodes), json.dumps(connections),
              ref["settings"] or "{}", ref["staticData"] or "{}",
              version_id, now, wf_id))
        print(f"Atualizado: {name}")
    else:
        conn.execute("""
            INSERT INTO workflow_entity
            (id, name, active, nodes, connections, settings, staticData,
             versionId, triggerCount, createdAt, updatedAt)
            VALUES (?,?,1,?,?,?,?,?,1,?,?)
        """, (wf_id, name, json.dumps(nodes), json.dumps(connections),
              ref["settings"] or "{}", ref["staticData"] or "{}",
              version_id, now, now))
        print(f"Criado: {name} ({wf_id})")

conn.commit()
conn.close()
print("\nPronto. Reinicie o n8n para ver os 3 novos workflows.")
