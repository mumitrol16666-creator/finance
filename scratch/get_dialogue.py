import json
import os

log_path = r"C:\Users\usace\.gemini\antigravity\brain\ec15e360-00e9-46a7-8ec8-fe2de715d98b\.system_generated\logs\transcript.jsonl"
if not os.path.exists(log_path):
    print("Log path does not exist:", log_path)
    exit(1)

dialogue = []
current_user = None

for line in open(log_path, "r", encoding="utf-8"):
    try:
        data = json.loads(line)
        source = data.get("source")
        type_ = data.get("type")
        content = data.get("content") or ""
        
        if type_ == "USER_INPUT":
            if current_user:
                dialogue.append(("User", current_user))
            current_user = content
        elif source == "MODEL" and type_ == "PLANNER_RESPONSE" and not data.get("tool_calls"):
            # This is a message sent to user (no tool calls)
            if current_user:
                dialogue.append(("User", current_user))
                current_user = None
            dialogue.append(("Model", content))
    except Exception as e:
        pass

if current_user:
    dialogue.append(("User", current_user))

# Print the last 15 exchanges
for role, text in dialogue[-15:]:
    print(f"[{role}]: {text.strip()[:300]}...")
    print("-" * 50)
