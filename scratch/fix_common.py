with open('app/handlers/common.py', 'rb') as f:
    content = f.read()

bad_pattern = b'await c.answerdef _upgrade_message'
if bad_pattern in content:
    content = content.replace(bad_pattern, b'await c.answer()\n\n\ndef _upgrade_message')
    with open('app/handlers/common.py', 'wb') as out:
        out.write(content)
    print("Fixed line 480!")
else:
    print("Pattern not found!")
