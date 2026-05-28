"""
Adiciona 3 workflows de disparo editorial ao n8n:
- 06:30 → morning dispatch
- 11:30 → noon dispatch
- 17:30 → evening dispatch
"""
import sqlite3, json
from datetime import datetime, timezone

DB = r"C:\Users\robep\.n8n\database.sqlite"
PYTHON = r"C:\Users\robep\Desktop\news_radar_rss\.venv\Scripts\python.exe"
CWD = r"C:\Users\robep\Desktop\news_radar_rss"

CRED_ID = "d02309d63d0c4d56"
CHAT_ID = "8773271293"

DISPATCH_EDITIONS = [
    ("morning", 6, 30, "Manhã (7h)"),
    ("noon",   11, 30, "Meio-dia (12h)"),
    ("evening",17, 30, "Tarde (18h)"),
]


def make_dispatch_workflow(edition: str, hour: int, minute: int, label: str) -> dict:
    js_dispatch = f"""
const {{ execSync }} = require('child_process');
const PYTHON = {json.dumps(PYTHON)};
const CWD = {json.dumps(CWD)};
try {{
  const out = execSync(
    `"${{PYTHON}}" -m news_radar.cli dispatch --edition {edition} --scope brasil --top 3`,
    {{ cwd: CWD, timeout: 60000, encoding: 'utf8' }}
  );
  try {{ return [{{ json: JSON.parse(out) }}]; }}
  catch {{ return [{{ json: {{ ok: true, output: out.trim().slice(0,300) }} }}]; }}
}} catch(e) {{
  return [{{ json: {{ ok: false, error: String(e.stderr || e.message || e).slice(0,300) }} }}];
}}""".strip()

    nodes = [
        {
            "id": f"sched-{edition}",
            "name": f"Schedule {label}",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.3,
            "position": [0, 300],
            "parameters": {
                "rule": {
                    "interval": [{
                        "field": "cronExpression",
                        "expression": f"{minute} {hour} * * *",  # hora e minuto fixos
                    }]
                }
            },
        },
        {
            "id": f"dispatch-{edition}",
            "name": f"Dispatch {label}",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [240, 300],
            "parameters": {"mode": "runOnceForAllItems", "jsCode": js_dispatch},
            "continueOnFail": True,
        },
        {
            "id": f"notify-{edition}",
            "name": f"Notify {label}",
            "type": "n8n-nodes-base.telegram",
            "typeVersion": 1.2,
            "position": [480, 300],
            "credentials": {"telegramApi": {"id": CRED_ID, "name": "News Radar Telegram Bot"}},
            "parameters": {
                "resource": "message",
                "operation": "sendMessage",
                "chatId": CHAT_ID,
                "text": f"={{ $json.ok ? '*Disparo {label} enviado!* ' + $json.dispatched + ' artigo(s) aguardando aprovação.' : '*Erro no disparo {label}:* ' + $json.error }}",
                "additionalFields": {"parse_mode": "Markdown"},
            },
            "continueOnFail": True,
            "executeOnce": True,
        },
    ]

    connections = {
        f"Schedule {label}":  {"main": [[{"node": f"Dispatch {label}",  "type": "main", "index": 0}]]},
        f"Dispatch {label}":  {"main": [[{"node": f"Notify {label}",    "type": "main", "index": 0}]]},
    }

    return {
        "name": f"News Radar — Disparo {label}",
        "nodes": json.dumps(nodes),
        "connections": json.dumps(connections),
        "active": 1,
        "settings": "{}",
        "staticData": "{}",
    }


conn = sqlite3.connect(DB)
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000")

for edition, hour, minute, label in DISPATCH_EDITIONS:
    wf = make_dispatch_workflow(edition, hour, minute, label)

    # Verifica se já existe
    existing = conn.execute(
        "SELECT id FROM workflow_entity WHERE name = ?", (wf["name"],)
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE workflow_entity SET nodes=?, connections=?, active=1, updatedAt=? WHERE id=?",
            (wf["nodes"], wf["connections"], now, existing[0])
        )
        print(f"Atualizado: {wf['name']}")
    else:
        import uuid
        wf_id = uuid.uuid4().hex[:16]
        version_id = uuid.uuid4().hex
        conn.execute(
            """INSERT INTO workflow_entity
               (id, name, nodes, connections, active, settings, staticData,
                versionId, triggerCount, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (wf_id, wf["name"], wf["nodes"], wf["connections"],
             wf["active"], wf["settings"], wf["staticData"],
             version_id, 1, now, now)
        )
        print(f"Criado: {wf['name']} (ID: {wf_id})")

conn.commit()
conn.close()

print("\n3 workflows de disparo editorial criados/atualizados.")
print("Reinicie o n8n para ativar os schedules.")
