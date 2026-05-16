import ast
import traceback

file_path = r'c:\FinanceBot\app\handlers\settings.py'
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        source = f.read()
    ast.parse(source)
    print("Syntax OK")
except SyntaxError:
    traceback.print_exc()
except Exception as e:
    print(f"Other error: {e}")
