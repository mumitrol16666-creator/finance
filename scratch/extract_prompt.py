import json
import os

log_path = r"C:\Users\usace\.gemini\antigravity\brain\ca3214e2-cd45-4005-b4b8-f98360287c28\.system_generated\logs\transcript.jsonl"
out_path = r"c:\FinanceBot\scratch\prompt_utf8.txt"
if os.path.exists(log_path):
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if '"step_index":1442' in line:
                try:
                    data = json.loads(line)
                    content = data.get("content")
                    with open(out_path, "w", encoding="utf-8") as out:
                        out.write(content)
                    print(f"Written to {out_path}")
                except Exception as e:
                    print(f"Error parsing JSON: {e}")
else:
    print(f"File not found: {log_path}")
