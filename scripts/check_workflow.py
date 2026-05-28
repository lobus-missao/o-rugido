import sqlite3, json

DB = r"C:\Users\robep\.n8n\database.sqlite"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

row = conn.execute("SELECT nodes, active FROM workflow_entity WHERE id = ?", ("wP740vEMvW5QsJwQ",)).fetchone()
nodes = json.loads(row["nodes"])
print("Workflow ativo:", row["active"])
print(f"Total nos: {len(nodes)}")
print()

for n in nodes:
    t = n.get("type", "")
    name = n.get("name", "?")
    if "code" in t:
        icon = "CODE "
    elif "telegram" in t and "Trigger" in t:
        icon = "TG-TR"
    elif "telegram" in t:
        icon = "TG   "
    elif "schedule" in t:
        icon = "SCHED"
    else:
        icon = t.split(".")[-1][:5].upper()
    print(f"  [{icon}] {name}")

conn.close()
