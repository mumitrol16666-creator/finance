import json
import os

log_path = r"C:\Users\usace\.gemini\antigravity\brain\ec15e360-00e9-46a7-8ec8-fe2de715d98b\.system_generated\logs\transcript.jsonl"
if not os.path.exists(log_path):
    print("Log path does not exist:", log_path)
    exit(1)

lines = open(log_path, "r", encoding="utf-8").readlines()
print(f"Total lines: {len(lines)}")
for line in lines[-20:]:
    try:
        data = json.loads(line)
        print("Source:", data.get("source"), "Type:", data.get("type"), "Content keys:", [k for k in data.keys() if k != "content"])
        if "content" in data and data.get("source") == "MODEL":
            c = data["content"]
            # print first 100 chars
            print("  Content preview:", repr(c[:100]))
    except Exception as e:
        print("Error parsing line:", e)
