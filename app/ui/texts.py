# app/ui/texts.py
# User-facing copy for onboarding (Telegram HTML parse mode).

TEXTS = {
    "ru": {
        "START_INTRO": (
            "✨ <b>Добро пожаловать!</b>\n\n"
            "Я помогу навести порядок в деньгах без таблиц и лишней суеты.\n\n"
            "<b>За минуту настройки:</b>\n"
            "1️⃣ Выберем валюту учёта.\n"
            "2️⃣ Добавим первый счёт или карту.\n"
            "3️⃣ При желании включим вечерний отчёт.\n\n"
            "<i>Можно начать прямо сейчас.</i>"
        ),
        "BTN_CANCEL": "❌ Отмена",
        "ASK_CURRENCY": (
            "🌍 <b>Шаг 1 из 3: валюта</b>\n\n"
            "В этой валюте будут показаны суммы и отчёты.\n\n"
            "Выбери валюту ниже:"
        ),
        "ASK_ACC_NAME": (
            "🏦 <b>Шаг 2 из 3: первый счёт</b>\n\n"
            "Как назовём кошелёк, карту или наличные?\n\n"
            "<i>Примеры: Kaspi, Наличные, Halyk</i>"
        ),
        "ASK_ACC_BAL": (
            "💵 <b>Текущий баланс</b>\n\n"
            "Введи сумму на счёте сейчас — с неё начнётся учёт.\n\n"
            "Только цифры, например <code>350000</code> или <code>0</code>."
        ),
        "ASK_ADD_MORE": (
            "✅ <b>Счёт добавлен</b>\n\n"
            "Добавить ещё один счёт или карту?"
        ),
        "ASK_DAILY": (
            "📊 <b>Шаг 3 из 3: вечерний отчёт</b>\n\n"
            "Раз в день бот может прислать итог:\n"
            "🟢 доходы\n"
            "🔴 расходы\n"
            "🔥 серия активности\n\n"
            "Включить ежедневный отчёт?"
        ),
        "ASK_DAILY_TIME": (
            "⏰ <b>Время отчёта</b>\n\n"
            "Выбери время ниже или введи своё, например <code>21:00</code>."
        ),
        "DONE": (
            "👑 <b>Готово, настройка завершена</b>\n\n"
            "Нажми <b>Расход</b> или <b>Доход</b> в меню и внеси первую операцию."
        ),
        "NEED_ONBOARD": "⚙️ Сначала пройди настройку.\nНажми /start.",
        "CURRENCY_SAVED": "✅ Валюта: <b>{cur}</b>",
        "NAME_ERROR": "⚠️ Название — от <b>2</b> до <b>24</b> символов.\n<i>Пример: Kaspi</i>",
        "SUM_ERROR": "⚠️ Введи сумму цифрами.\n<i>Пример: 350000</i>",
        "NEED_ONE_ACCOUNT": "Нужен хотя бы один счёт",
        "CUSTOM_TIME": "✍️ Введи время, например <code>21:00</code>",
        "TIME_ERROR": "⚠️ Не похоже на время. Пример: <code>21:00</code>",
        "MENU": "📌 <b>Меню</b>",
    },
    "en": {
        "START_INTRO": (
            "✨ <b>Welcome!</b>\n\n"
            "I'll help you track money without spreadsheets or clutter.\n\n"
            "<b>One-minute setup:</b>\n"
            "1️⃣ Choose your currency.\n"
            "2️⃣ Add your first account or card.\n"
            "3️⃣ Optionally enable a daily summary.\n\n"
            "<i>You can start right away.</i>"
        ),
        "BTN_CANCEL": "❌ Cancel",
        "ASK_CURRENCY": (
            "🌍 <b>Step 1 of 3: currency</b>\n\n"
            "Amounts and reports will use this currency.\n\n"
            "Choose below:"
        ),
        "ASK_ACC_NAME": (
            "🏦 <b>Step 2 of 3: first account</b>\n\n"
            "What should we call this wallet, card, or cash?\n\n"
            "<i>Examples: Kaspi, Cash, Bank card</i>"
        ),
        "ASK_ACC_BAL": (
            "💵 <b>Current balance</b>\n\n"
            "Enter the balance on this account now.\n\n"
            "Digits only, e.g. <code>350000</code> or <code>0</code>."
        ),
        "ASK_ADD_MORE": (
            "✅ <b>Account saved</b>\n\n"
            "Add another account or card?"
        ),
        "ASK_DAILY": (
            "📊 <b>Step 3 of 3: daily summary</b>\n\n"
            "Once a day the bot can send:\n"
            "🟢 income\n"
            "🔴 expenses\n"
            "🔥 activity streak\n\n"
            "Enable the daily report?"
        ),
        "ASK_DAILY_TIME": (
            "⏰ <b>Report time</b>\n\n"
            "Pick a time below or type your own, e.g. <code>21:00</code>."
        ),
        "DONE": (
            "👑 <b>Setup complete</b>\n\n"
            "Tap <b>Expense</b> or <b>Income</b> in the menu and log your first transaction."
        ),
        "NEED_ONBOARD": "⚙️ Please complete setup first.\nTap /start.",
        "CURRENCY_SAVED": "✅ Currency: <b>{cur}</b>",
        "NAME_ERROR": "⚠️ Name must be <b>2–24</b> characters.\n<i>Example: Kaspi</i>",
        "SUM_ERROR": "⚠️ Enter the amount using digits only.\n<i>Example: 350000</i>",
        "NEED_ONE_ACCOUNT": "At least one account is required",
        "CUSTOM_TIME": "✍️ Enter time, e.g. <code>21:00</code>",
        "TIME_ERROR": "⚠️ That doesn't look like a time. Example: <code>21:00</code>",
        "MENU": "📌 <b>Menu</b>",
    },
    "kk": {
        "START_INTRO": (
            "✨ <b>Қош келдіңіз!</b>\n\n"
            "Кестесіз және артық батырмасыз ақша есебіне көмектесемін.\n\n"
            "<b>Бір минуттық баптау:</b>\n"
            "1️⃣ Валютаны таңдаймыз.\n"
            "2️⃣ Алғашқы шотты немесе картаны қосамыз.\n"
            "3️⃣ Қалауыңыз бойынша күндік есепті қосамыз.\n\n"
            "<i>Дәл қазір бастауға болады.</i>"
        ),
        "BTN_CANCEL": "❌ Болдырмау",
        "ASK_CURRENCY": (
            "🌍 <b>1-қадам (барлығы 3): валюта</b>\n\n"
            "Сомалар мен есептер осы валютада көрсетіледі.\n\n"
            "Төменнен таңдаңыз:"
        ),
        "ASK_ACC_NAME": (
            "🏦 <b>2-қадам (барлығы 3): алғашқы шот</b>\n\n"
            "Әмиян, карта немесе қолма-қол ақшаны қалай атаймыз?\n\n"
            "<i>Мысалдар: Kaspi, Қолма-қол, Halyk</i>"
        ),
        "ASK_ACC_BAL": (
            "💵 <b>Ағымдағы баланс</b>\n\n"
            "Шоттағы қазіргі соманы енгізіңіз.\n\n"
            "Тек сандар, мысалы <code>350000</code> немесе <code>0</code>."
        ),
        "ASK_ADD_MORE": (
            "✅ <b>Шот сақталды</b>\n\n"
            "Тағы бір шот немесе карта қосу керек пе?"
        ),
        "ASK_DAILY": (
            "📊 <b>3-қадам (барлығы 3): күндік есеп</b>\n\n"
            "Күніне бір рет бот жібере алады:\n"
            "🟢 кірістер\n"
            "🔴 шығыстар\n"
            "🔥 белсенділік сериясы\n\n"
            "Күнделікті есепті қосамыз ба?"
        ),
        "ASK_DAILY_TIME": (
            "⏰ <b>Есеп уақыты</b>\n\n"
            "Төменнен таңдаңыз немесе өз уақытыңызды жазыңыз, мысалы <code>21:00</code>."
        ),
        "DONE": (
            "👑 <b>Баптау аяқталды</b>\n\n"
            "Мәзірдегі <b>Шығыс</b> немесе <b>Кіріс</b> түймесін басып, алғашқы операцияны енгізіңіз."
        ),
        "NEED_ONBOARD": "⚙️ Алдымен баптауды аяқтаңыз.\n/start басыңыз.",
        "CURRENCY_SAVED": "✅ Валюта: <b>{cur}</b>",
        "NAME_ERROR": "⚠️ Атауы <b>2–24</b> таңба болуы керек.\n<i>Мысал: Kaspi</i>",
        "SUM_ERROR": "⚠️ Соманы тек сандармен енгізіңіз.\n<i>Мысал: 350000</i>",
        "NEED_ONE_ACCOUNT": "Кемінде бір шот қажет",
        "CUSTOM_TIME": "✍️ Уақытты жазыңыз, мысалы <code>21:00</code>",
        "TIME_ERROR": "⚠️ Уақыт түсінілмеді. Мысал: <code>21:00</code>",
        "MENU": "📌 <b>Мәзір</b>",
    },
}

def get_text(lang: str, key: str, **kwargs) -> str:
    lang = (lang or "ru").lower()
    base = TEXTS.get(lang, TEXTS["ru"]).get(key, TEXTS["ru"].get(key, key))
    return base.format(**kwargs) if kwargs else base

# backward compatibility
START_INTRO = TEXTS["ru"]["START_INTRO"]
DONE = TEXTS["ru"]["DONE"]
BTN_CANCEL = TEXTS["ru"]["BTN_CANCEL"]
ASK_CURRENCY = TEXTS["ru"]["ASK_CURRENCY"]
ASK_ACC_NAME = TEXTS["ru"]["ASK_ACC_NAME"]
ASK_ACC_BAL = TEXTS["ru"]["ASK_ACC_BAL"]
ASK_ADD_MORE = TEXTS["ru"]["ASK_ADD_MORE"]
ASK_DAILY = TEXTS["ru"]["ASK_DAILY"]
ASK_DAILY_TIME = TEXTS["ru"]["ASK_DAILY_TIME"]
NEED_ONBOARD = TEXTS["ru"]["NEED_ONBOARD"]
