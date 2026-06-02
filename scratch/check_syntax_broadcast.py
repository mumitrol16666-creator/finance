import ast
import sys

files = [
    r'c:\FinanceBot\app\config\settings.py',
    r'c:\FinanceBot\app\db\repositories\users_repo.py',
    r'c:\FinanceBot\app\handlers\teaser_broadcast.py',
    r'c:\FinanceBot\app\handlers\__init__.py',
]

for file_path in files:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        print(f"{file_path}: Syntax OK")
    except SyntaxError as e:
        print(f"Syntax Error in {file_path}: {e.msg} at line {e.lineno}, offset {e.offset}")
        print(f"Line content: {e.text}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        sys.exit(1)

print("All files compiled successfully!")
