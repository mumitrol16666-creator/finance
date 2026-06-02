with open(r"c:\FinanceBot\app\domain\services\ai_consultant_service.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

out_path = r"c:\FinanceBot\scratch\upper_lines_utf8.txt"
with open(out_path, "w", encoding="utf-8") as out:
    # Let's search for build_period_meta
    start_line = -1
    for idx, line in enumerate(lines):
        if "def build_period_meta" in line:
            start_line = idx
            break
    if start_line != -1:
        for idx in range(start_line, min(start_line + 80, len(lines))):
            out.write(f"{idx + 1}: {lines[idx]}")
    else:
        out.write("Not found")

print("Saved to", out_path)
