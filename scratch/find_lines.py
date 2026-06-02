import inspect

with open(r"c:\FinanceBot\app\domain\services\ai_consultant_service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

start_line = -1
for idx, line in enumerate(lines):
    if "async def build_ai_context" in line:
        start_line = idx
        break

if start_line != -1:
    print(f"Found build_ai_context at line {start_line + 1}")
    # print the next 200 lines
    for idx in range(start_line, min(start_line + 200, len(lines))):
        print(f"{idx + 1}: {lines[idx]}", end="")
else:
    print("build_ai_context not found")
