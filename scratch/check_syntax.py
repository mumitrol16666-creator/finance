import ast
import sys

file_path = r'c:\FinanceBot\app\handlers\settings.py'
try:
    with open(file_path, 'r', encoding='utf-8') as f:
        source = f.read()
    ast.parse(source)
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax Error: {e.msg} at line {e.lineno}, offset {e.offset}")
    print(f"Line content: {e.text}")
except Exception as e:
    print(f"Error: {e}")
