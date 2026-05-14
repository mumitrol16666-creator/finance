$content = [System.IO.File]::ReadAllText("c:\FinanceBot\app\handlers\common.py", [System.Text.Encoding]::UTF8)

# Replace literal \uXXXX escape sequences with actual Unicode characters
# Line 112: emoji tokens
$content = $content.Replace("('\u274c', '\u26d4', '\u2716', '\u2715', '\u00d7')", "('$([char]0x274c)', '$([char]0x26d4)', '$([char]0x2716)', '$([char]0x2715)', '$([char]0x00d7)')")

# Line 115: Russian cancel words
$old115 = "'\u043e\u0442\u043c\u0435\u043d\u0430', '\u043e\u0442\u043c\u0435\u043d\u0438\u0442\u044c', '/cancel', 'cancel', '\u0431\u043e\u043b\u0434\u044b\u0440\u043c\u0430\u0443'"
$otmena = "$([char]0x043e)$([char]0x0442)$([char]0x043c)$([char]0x0435)$([char]0x043d)$([char]0x0430)"
$otmenit = "$([char]0x043e)$([char]0x0442)$([char]0x043c)$([char]0x0435)$([char]0x043d)$([char]0x0438)$([char]0x0442)$([char]0x044c)"
$boldyrmau = "$([char]0x0431)$([char]0x043e)$([char]0x043b)$([char]0x0434)$([char]0x044b)$([char]0x0440)$([char]0x043c)$([char]0x0430)$([char]0x0443)"
$new115 = "'$otmena', '$otmenit', '/cancel', 'cancel', '$boldyrmau'"
$content = $content.Replace($old115, $new115)

$enc = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText("c:\FinanceBot\app\handlers\common.py", $content, $enc)
Write-Output "Done fixing is_cancel_text"
