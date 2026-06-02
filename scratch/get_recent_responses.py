import json
import os

log_path = r"C:\Users\usace\.gemini\antigravity\brain\ec15e360-00e9-46a7-8ec8-fe2de715d98b\.system_generated\logs\transcript.jsonl"
if not os.path.exists(log_path):
    print("Log path does not exist:", log_path)
    exit(1)

model_responses = []
for line in open(log_path, "r", encoding="utf-8"):
    try:
        data = json.loads(line)
        if data.get("source") == "MODEL" and data.get("type") == "PLANNER_RESPONSE":
            content = data.get("content")
            if content:
                model_responses.append(content)
    except Exception as e:
        pass

# Print the last 3 model responses
for idx in range(max(0, len(model_responses)-3), len(model_responses)):
    print(f"--- Response {idx} ---")
    print(model_responses[idx])
