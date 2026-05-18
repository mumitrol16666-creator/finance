import sys

file_path = "app/ui/i18n.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

ru_target = '"TX_TR_CONFIRM_PROCEED": "Выполнить перевод?",'
ru_additions = """"TX_TR_CONFIRM_PROCEED": "Выполнить перевод?",
        "TX_SUM": "💸 Сумма",
        "TX_ACC": "💳 Счёт",
        "TX_CAT": "🧾 Категория",
        "TX_NOTE": "📝 Комментарий",
        "TX_FROM": "📤 Откуда",
        "TX_TO": "📥 Куда",
        "TX_INC_CAT": "💼 Категория",
        "TX_INC_SUM": "💵 Сумма",
        "TX_EDIT_CAT": "✏️ Категория",
        "TX_EDIT_NOTE": "✏️ Комментарий",
        "TX_EDIT_FROM": "✏️ Откуда",
        "TX_EDIT_TO": "✏️ Куда",
        "TX_BTN_PROCEED_TR": "✅ Выполнить",
        "TX_EXP_SUCCESS": "✅ <b>Расход добавлен</b>",
        "TX_INC_SUCCESS": "✅ <b>Доход добавлен</b>",
        "TX_TR_SUCCESS": "🔁 <b>Перевод между счетами выполнен</b>",
        "TX_DAILY_LIMIT_WARN": "\\n\\n⚠️ Почти дневной лимит. Остаток: <b>{left}</b>",
        "TX_DAILY_LIMIT_OVER": "\\n\\nПревышение дневного лимита: {left}",
        "TX_DAILY_LIMIT_HARD_OVER": "\\n\\n🚫 Жёсткое превышение дневного лимита: <b>{left}</b>",
        "TX_CAT_LIMIT_WARN": "\\n\\n⚠️ Почти лимит категории ({month}). Остаток: <b>{left}</b>",
        "TX_CAT_LIMIT_OVER": "\\n\\nПревышение лимита категории ({month}): {left}",
        "TX_CAT_LIMIT_HARD_OVER": "\\n\\n🚫 Жёсткий перерасход по категории ({month}): <b>{left}</b>",
        "TX_INC_MONTH_TOTAL": "📈 Доход за {month}: <b>{total}</b>",
        "TX_INC_MONTH_COUNT": "🧾 Операций за {month}: <b>{count}</b>",
        "TX_INC_CAT_MONTH_TOTAL": "💼 По категории за {month}: <b>{total}</b>",
        "TX_INC_MONTH_MAX": "🏆 Крупнейший доход месяца: <b>{total}</b>",
        "TX_INC_MONTH_GROWTH": "↗️ К {month}: <b>+{delta}</b>",
        "TX_INC_MONTH_DECLINE": "↘️ К {month}: <b>-{delta}</b>",
        "TX_INC_MONTH_EQUAL": "➡️ К {month}: <b>без изменений</b>",
        "TX_INC_MONTH_NO_DATA": "📁 За {month}: <b>нет данных</b>","""

en_target = '"TX_TR_CONFIRM_PROCEED": "Execute transfer?",'
en_additions = """"TX_TR_CONFIRM_PROCEED": "Execute transfer?",
        "TX_SUM": "💸 Amount",
        "TX_ACC": "💳 Account",
        "TX_CAT": "🧾 Category",
        "TX_NOTE": "📝 Comment",
        "TX_FROM": "📤 From",
        "TX_TO": "📥 To",
        "TX_INC_CAT": "💼 Category",
        "TX_INC_SUM": "💵 Amount",
        "TX_EDIT_CAT": "✏️ Category",
        "TX_EDIT_NOTE": "✏️ Comment",
        "TX_EDIT_FROM": "✏️ From",
        "TX_EDIT_TO": "✏️ To",
        "TX_BTN_PROCEED_TR": "✅ Execute",
        "TX_EXP_SUCCESS": "✅ <b>Expense added</b>",
        "TX_INC_SUCCESS": "✅ <b>Income added</b>",
        "TX_TR_SUCCESS": "🔁 <b>Transfer between accounts completed</b>",
        "TX_DAILY_LIMIT_WARN": "\\n\\n⚠️ Almost reached daily limit. Remaining: <b>{left}</b>",
        "TX_DAILY_LIMIT_OVER": "\\n\\nDaily limit exceeded: {left}",
        "TX_DAILY_LIMIT_HARD_OVER": "\\n\\n🚫 Hard daily limit exceeded: <b>{left}</b>",
        "TX_CAT_LIMIT_WARN": "\\n\\n⚠️ Almost reached category limit ({month}). Remaining: <b>{left}</b>",
        "TX_CAT_LIMIT_OVER": "\\n\\nCategory limit exceeded ({month}): {left}",
        "TX_CAT_LIMIT_HARD_OVER": "\\n\\n🚫 Hard category limit exceeded ({month}): <b>{left}</b>",
        "TX_INC_MONTH_TOTAL": "📈 Income for {month}: <b>{total}</b>",
        "TX_INC_MONTH_COUNT": "🧾 Transactions for {month}: <b>{count}</b>",
        "TX_INC_CAT_MONTH_TOTAL": "💼 For category in {month}: <b>{total}</b>",
        "TX_INC_MONTH_MAX": "🏆 Largest income of the month: <b>{total}</b>",
        "TX_INC_MONTH_GROWTH": "↗️ vs {month}: <b>+{delta}</b>",
        "TX_INC_MONTH_DECLINE": "↘️ vs {month}: <b>-{delta}</b>",
        "TX_INC_MONTH_EQUAL": "➡️ vs {month}: <b>no changes</b>",
        "TX_INC_MONTH_NO_DATA": "📁 For {month}: <b>no data</b>","""

kk_target = '"TX_TR_CONFIRM_PROCEED": "Аударымды орындаймыз ба?",'
kk_additions = """"TX_TR_CONFIRM_PROCEED": "Аударымды орындаймыз ба?",
        "TX_SUM": "💸 Сомасы",
        "TX_ACC": "💳 Шот",
        "TX_CAT": "🧾 Санат",
        "TX_NOTE": "📝 Түсініктеме",
        "TX_FROM": "📤 Қайдан",
        "TX_TO": "📥 Қайда",
        "TX_INC_CAT": "💼 Санат",
        "TX_INC_SUM": "💵 Сомасы",
        "TX_EDIT_CAT": "✏️ Санат",
        "TX_EDIT_NOTE": "✏️ Түсініктеме",
        "TX_EDIT_FROM": "✏️ Қайдан",
        "TX_EDIT_TO": "✏️ Қайда",
        "TX_BTN_PROCEED_TR": "✅ Орындау",
        "TX_EXP_SUCCESS": "✅ <b>Шығыс қосылды</b>",
        "TX_INC_SUCCESS": "✅ <b>Кіріс қосылды</b>",
        "TX_TR_SUCCESS": "🔁 <b>Шоттар арасындағы аударым орындалды</b>",
        "TX_DAILY_LIMIT_WARN": "\\n\\n⚠️ Күнделікті лимитке жақын. Қалдық: <b>{left}</b>",
        "TX_DAILY_LIMIT_OVER": "\\n\\nКүнделікті лимиттен асып кету: {left}",
        "TX_DAILY_LIMIT_HARD_OVER": "\\n\\n🚫 Күнделікті лимитті қатаң асыру: <b>{left}</b>",
        "TX_CAT_LIMIT_WARN": "\\n\\n⚠️ Санат лимитіне жақын ({month}). Қалдық: <b>{left}</b>",
        "TX_CAT_LIMIT_OVER": "\\n\\nСанат лимітінен асып кету ({month}): {left}",
        "TX_CAT_LIMIT_HARD_OVER": "\\n\\n🚫 Санат бойынша қатаң артық шығыс ({month}): <b>{left}</b>",
        "TX_INC_MONTH_TOTAL": "📈 {month} айындағы кіріс: <b>{total}</b>",
        "TX_INC_MONTH_COUNT": "🧾 {month} айындағы операциялар: <b>{count}</b>",
        "TX_INC_CAT_MONTH_TOTAL": "💼 Санат бойынша {month} айында: <b>{total}</b>",
        "TX_INC_MONTH_MAX": "🏆 Айдың ең көп кірісі: <b>{total}</b>",
        "TX_INC_MONTH_GROWTH": "↗️ {month} айымен салыстырғанда: <b>+{delta}</b>",
        "TX_INC_MONTH_DECLINE": "↘️ {month} айымен салыстырғанда: <b>-{delta}</b>",
        "TX_INC_MONTH_EQUAL": "➡️ {month} айымен салыстырғанда: <b>өзгеріссіз</b>",
        "TX_INC_MONTH_NO_DATA": "📁 {month} үшін: <b>деректер жоқ</b>","""

if ru_target not in content:
    print("ru target not found!")
    sys.exit(1)
content = content.replace(ru_target, ru_additions, 1)

if en_target not in content:
    print("en target not found!")
    sys.exit(1)
content = content.replace(en_target, en_additions, 1)

if kk_target not in content:
    print("kk target not found!")
    sys.exit(1)
content = content.replace(kk_target, kk_additions, 1)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Successfully added final success & summary i18n keys!")
