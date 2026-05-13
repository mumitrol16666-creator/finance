# app/ui/texts.py

TEXTS = {
    "ru": {
        "START_INTRO": "💰 **Личный учёт денег без таблиц и каши**\n\nСначала бот открывает только базовые разделы, чтобы ты не утонул в кнопках.\n\nЧто будет сразу:\n• доходы и расходы\n• история\n• настройки\n\nПосле активности откроются отчёты и счета. Полный режим можно включить отдельно.\n\n⚙️ Настройка займёт меньше минуты.",
        "BTN_CANCEL": "❌ Отмена",
        "ASK_CURRENCY": "🌍 **Выбери валюту учёта**\n\nВ ней будут отображаться все суммы.",
        "ASK_ACC_NAME": "🏦 **Добавим первый счёт**\n\nКак назвать?\n_Примеры: Kaspi, Наличные, Депозит_",
        "ASK_ACC_BAL": "💵 **Укажи текущий баланс**\n\nВведи сумму цифрами.\n_Например: 350000_\n\nЕсли баланс нулевой — просто `0`.",
        "ASK_ADD_MORE": "✅ **Счёт сохранён**\n\nДобавить ещё один?",
        "ASK_DAILY": "📊 **Включить ежедневный отчёт?**\n\nРаз в день бот пришлёт итог:\n• доходы\n• расходы\n• результат дня",
        "ASK_DAILY_TIME": "⏰ **Во сколько присылать отчёт?**\n\nВыбери время ниже или введи своё в формате `HH:MM`.",
        "DONE": "🎯 **Готово. Настройка завершена.**\n\nСейчас открыт базовый режим: доходы, расходы, история и настройки.\nПосле серии активности откроются отчёты и счета.\nЕсли нужен полный набор разделов сразу — в меню есть кнопка **Все возможности**.",
        "NEED_ONBOARD": "⚙️ Сначала нужна настройка.\nНажми /start.",
        "CURRENCY_SAVED": "✅ Валюта сохранена: **{cur}**",
        "NAME_ERROR": "⚠️ Название должно быть **2–24 символа**.\n_Пример: Kaspi_",
        "SUM_ERROR": "⚠️ Введи сумму **только цифрами**.\n_Пример: 350000_",
        "NEED_ONE_ACCOUNT": "Нужен хотя бы 1 счёт",
        "CUSTOM_TIME": "✍️ Введи время в формате `HH:MM`",
        "TIME_ERROR": "⚠️ Формат `HH:MM`, пример `21:00`",
        "MENU": "📌 **Меню:**",
    },
    "en": {
        "START_INTRO": "💰 **Personal money tracking without spreadsheets or clutter**\n\nAt first the bot shows only the basic sections, so you do not drown in buttons.\n\nYou get right away:\n• income and expense tracking\n• history\n• settings\n\nAfter some activity, reports and accounts will open. Full mode can be enabled separately.\n\n⚙️ Setup takes less than a minute.",
        "BTN_CANCEL": "❌ Cancel",
        "ASK_CURRENCY": "🌍 **Choose your accounting currency**\n\nAll amounts will be shown in it.",
        "ASK_ACC_NAME": "🏦 **Let's add your first account**\n\nWhat should it be called?\n_Examples: Kaspi, Cash, Deposit_",
        "ASK_ACC_BAL": "💵 **Enter the current balance**\n\nType the amount in digits.\n_For example: 350000_\n\nIf the balance is zero, just enter `0`.",
        "ASK_ADD_MORE": "✅ **Account saved**\n\nAdd one more?",
        "ASK_DAILY": "📊 **Enable daily report?**\n\nOnce a day the bot will send:\n• income\n• expenses\n• daily result",
        "ASK_DAILY_TIME": "⏰ **What time should I send the report?**\n\nChoose below or enter your own time in `HH:MM` format.",
        "DONE": "🎯 **Done. Setup completed.**\n\nYou are now in the basic mode: income, expense, history and settings.\nAfter an activity streak, reports and accounts will open.\nIf you want everything right away, use the **All features** button in the menu.",
        "NEED_ONBOARD": "⚙️ Setup is required first.\nTap /start.",
        "CURRENCY_SAVED": "✅ Currency saved: **{cur}**",
        "NAME_ERROR": "⚠️ Name must be **2–24 characters**.\n_Example: Kaspi_",
        "SUM_ERROR": "⚠️ Enter the amount using **digits only**.\n_Example: 350000_",
        "NEED_ONE_ACCOUNT": "At least 1 account is required",
        "CUSTOM_TIME": "✍️ Enter time in `HH:MM` format",
        "TIME_ERROR": "⚠️ Use `HH:MM`, for example `21:00`",
        "MENU": "📌 **Menu:**",
    },
    "kk": {
        "START_INTRO": "💰 **Кестесіз және артық батырмасыз жеке қаржы есебі**\n\nАлғашында бот сені батырмалармен басып тастамайды, тек негізгі бөлімдерді көрсетеді.\n\nБірден қолжетімді:\n• кіріс пен шығыс\n• тарих\n• баптаулар\n\nБелсенділіктен кейін есептер мен шоттар ашылады. Толық режимді бөлек қосуға болады.\n\n⚙️ Баптау бір минуттан аз уақыт алады.",
        "BTN_CANCEL": "❌ Болдырмау",
        "ASK_CURRENCY": "🌍 **Есеп валютасын таңдаңыз**\n\nБарлық сома осы валютада көрсетіледі.",
        "ASK_ACC_NAME": "🏦 **Алғашқы шотты қосайық**\n\nҚалай атаймыз?\n_Мысалдар: Kaspi, Қолма-қол, Депозит_",
        "ASK_ACC_BAL": "💵 **Ағымдағы балансты енгізіңіз**\n\nСоманы цифрмен жазыңыз.\n_Мысалы: 350000_\n\nЕгер баланс нөл болса, жай ғана `0` енгізіңіз.",
        "ASK_ADD_MORE": "✅ **Шот сақталды**\n\nТағы біреуін қосу керек пе?",
        "ASK_DAILY": "📊 **Күнделікті есепті қосу керек пе?**\n\nКүніне бір рет бот мынаны жібереді:\n• кірістер\n• шығыстар\n• күн қорытындысы",
        "ASK_DAILY_TIME": "⏰ **Есепті қай уақытта жіберейін?**\n\nТөменнен таңдаңыз немесе `HH:MM` форматында енгізіңіз.",
        "DONE": "🎯 **Дайын. Баптау аяқталды.**\n\nҚазір базалық режим ашық: кіріс, шығыс, тарих және баптаулар.\nБелсенділік сериясынан кейін есептер мен шоттар ашылады.\nЕгер барлық бөлім бірден керек болса, мәзірдегі **Барлық мүмкіндік** батырмасын қолдан.\n",
        "NEED_ONBOARD": "⚙️ Алдымен баптау қажет.\n/start басыңыз.",
        "CURRENCY_SAVED": "✅ Валюта сақталды: **{cur}**",
        "NAME_ERROR": "⚠️ Атауы **2–24 таңба** болуы керек.\n_Мысал: Kaspi_",
        "SUM_ERROR": "⚠️ Соманы тек **цифрмен** енгізіңіз.\n_Мысал: 350000_",
        "NEED_ONE_ACCOUNT": "Кемінде 1 шот қажет",
        "CUSTOM_TIME": "✍️ Уақытты `HH:MM` форматында енгізіңіз",
        "TIME_ERROR": "⚠️ `HH:MM` форматын қолданыңыз, мысалы `21:00`",
        "MENU": "📌 **Мәзір:**",
    },
}

def get_text(lang: str, key: str, **kwargs) -> str:
    lang = (lang or 'ru').lower()
    base = TEXTS.get(lang, TEXTS['ru']).get(key, TEXTS['ru'].get(key, key))
    return base.format(**kwargs) if kwargs else base

# backward compatibility
START_INTRO = TEXTS['ru']['START_INTRO']
DONE = TEXTS['ru']['DONE']
BTN_CANCEL = TEXTS['ru']['BTN_CANCEL']
ASK_CURRENCY = TEXTS['ru']['ASK_CURRENCY']
ASK_ACC_NAME = TEXTS['ru']['ASK_ACC_NAME']
ASK_ACC_BAL = TEXTS['ru']['ASK_ACC_BAL']
ASK_ADD_MORE = TEXTS['ru']['ASK_ADD_MORE']
ASK_DAILY = TEXTS['ru']['ASK_DAILY']
ASK_DAILY_TIME = TEXTS['ru']['ASK_DAILY_TIME']
NEED_ONBOARD = TEXTS['ru']['NEED_ONBOARD']
