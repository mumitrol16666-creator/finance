import json
import os

log_path = r"C:\Users\usace\.gemini\antigravity\brain\ec15e360-00e9-46a7-8ec8-fe2de715d98b\.system_generated\logs\transcript.jsonl"
if not os.path.exists(log_path):
    print("Log path does not exist:", log_path)
    exit(1)

commands = []
for line in open(log_path, "r", encoding="utf-8"):
    try:
        data = json.loads(line)
        tool_calls = data.get("tool_calls", [])
        if not tool_calls:
            continue
        for tc in tool_calls:
            if tc.get("name") == "run_command":
                cmd = tc.get("args", {}).get("CommandLine")
                if cmd:
                    commands.append(cmd)
    except Exception as e:
        pass

for i, cmd in enumerate(commands):
    print(f"{i}: {cmd}")
