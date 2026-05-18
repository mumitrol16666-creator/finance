# app/ui/texts.py

TEXTS = {
    "ru": {
        "START_INTRO": "✨ **Добро пожаловать в мир финансового баланса!**\n\nЯ помогу тебе навсегда забыть о хаосе в деньгах, сложных Excel-таблицах и мучительных мыслях «куда делась зарплата».\n\n**Что мы сделаем за 45 секунд настройки:**\n1️⃣ Выберем основную валюту учёта.\n2️⃣ Добавим твой первый кошелёк или карту.\n3️⃣ Настроим отчёты и советы.\n\n*Твой путь к финансовой свободе начинается прямо сейчас.*",
        "BTN_CANCEL": "❌ Отмена",
        "ASK_CURRENCY": "🌍 **Шаг 1 из 3: Ваша главная валюта**\n\nВ этой валюте бот будет вести все расчеты, строить графики и показывать твой суммарный чистый капитал.\n\nВыбери основную валюту:",
        "ASK_ACC_NAME": "🏦 **Шаг 2 из 3: Твоя первая финансовая точка**\n\nДеньги не лежат в воздухе. Давай добавим твой первый кошелёк, карту или наличные.\n\n**Как мы его назовём?**\n_Примеры: Kaspi, Наличные, Halyk, Депозит_",
        "ASK_ACC_BAL": "💵 **Стартовый капитал**\n\nУкажи текущий баланс этого счёта. Это твоя точка отсчёта, с которой начнется финансовый трекинг.\n\nОтправь сумму **только цифрами** (например, `350000` или `0`):",
        "ASK_ADD_MORE": "✅ **Счёт успешно добавлен и готов к работе!**\n\nЕсть ли у тебя другие счета, карты или наличные, которые ты хочешь добавить прямо сейчас? Чем точнее общая сумма, тем лучше бот понимает твою финансовую картину.",
        "ASK_DAILY": "📊 **Шаг 3 из 3: Твой финансовый радар**\n\nУспешные люди подводят итоги каждый день. Бот может присылать тебе красивую вечернюю сводку:\n🟢 Твой чистый доход за день\n🔴 Твои расходы и топ категорий\n🔥 Твою непрерывную серию ведения бюджета\n\nВключаем Ежедневный отчёт?",
        "ASK_DAILY_TIME": "⏰ **Идеальное время для финансового пульса**\n\nВыбери удобное время, когда ты сможешь на 10 секунд заглянуть в бот и увидеть итог дня, или введи свое время в формате `HH:MM`:",
        "DONE": "👑 **Поздравляем! Базовая настройка завершена.**\n\nТы сделал первый и самый важный шаг к управлению своими деньгами.\n\n**Как вести учет в 1 клик:**\nПросто отправь боту сообщение в свободной форме, например: `1500 такси` или `5000 продукты` — и он всё поймет!\n\nВсе возможности бота открыты и готовы к работе. Давай начнем!",
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
        "START_INTRO": "✨ **Welcome to the world of financial balance!**\n\nI will help you forget about financial chaos, complicated Excel spreadsheets, and painful thoughts of 'where did all my money go'.\n\n**What we will do in 45 seconds of setup:**\n1️⃣ Choose your main accounting currency.\n2️⃣ Add your first card or cash balance.\n3️⃣ Configure smart reports and insights.\n\n*Your path to financial freedom starts right now.*",
        "BTN_CANCEL": "❌ Cancel",
        "ASK_CURRENCY": "🌍 **Step 1 of 3: Your main currency**\n\nAll calculations, reports, and your total net worth will be displayed in this currency.\n\nChoose your main currency below:",
        "ASK_ACC_NAME": "🏦 **Step 2 of 3: Your first account**\n\nMoney doesn't exist in a vacuum. Let's add your first wallet, card, or cash balance.\n\n**What should we call it?**\n_Examples: Kaspi, Cash, Bank Card, Savings_",
        "ASK_ACC_BAL": "💵 **Starting Balance**\n\nEnter the current balance of this account. This is your starting point for financial tracking.\n\nSend the amount **using digits only** (e.g. `350000` or `0`):",
        "ASK_ADD_MORE": "✅ **Account successfully saved and ready!**\n\nDo you have other bank cards, cash, or deposits you want to add right now? The more accurate your total capital, the better insights you get.",
        "ASK_DAILY": "📊 **Step 3 of 3: Your Financial Radar**\n\nSuccessful people review their progress daily. The bot can send you a beautiful evening summary:\n🟢 Your net income for the day\n🔴 Your expenses and top categories\n🔥 Your active budget tracking streak\n\nShould we enable the Daily Report?",
        "ASK_DAILY_TIME": "⏰ **The perfect time for your financial pulse**\n\nChoose a convenient time to take 10 seconds and look at your summary, or enter a custom time in `HH:MM` format:",
        "DONE": "👑 **Congratulations! Base setup completed.**\n\nYou have taken the first and most important step towards mastering your money.\n\n**How to log transactions in 1 click:**\nJust send a free-form message like `1500 taxi` or `5000 groceries` — and I will handle the rest!\n\nAll tools are open and ready for action. Let's begin!",
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
        "START_INTRO": "✨ **Қаржылық теңгерім әлеміне қош келдіңіз!**\n\nМен сізге ақшадағы ретсіздікті, күрделі Excel кестелерін және «жалақым қайда кетті» деген мазасыз ойларды мәңгілікке ұмытуға көмектесемін.\n\n**45 секундтық баптауда не істейміз:**\n1️⃣ Негізгі валютаны таңдаймыз.\n2️⃣ Алғашқы әмиянды немесе картаны қосамыз.\n3️⃣ Зерек есептер мен кеңестерді баптаймыз.\n\n*Сіздің қаржылық еркіндікке барар жолыңыз дәл қазір басталады.*",
        "BTN_CANCEL": "❌ Болдырмау",
        "ASK_CURRENCY": "🌍 **1-қадам (барлығы 3): Сіздің негізгі валютаңыз**\n\nОсы валютада бот барлық есептеулерді жүргізеді, графиктер салады және жалпы таза капиталыңызды көрсетеді.\n\nТөменнен негізгі валютаны таңдаңыз:",
        "ASK_ACC_NAME": "🏦 **2-қадам (барлығы 3): Алғашқы шотты қосу**\n\nАқша ауада тұрмайды. Алғашқы әмияныңызды, картаңызды немесе қолма-қол ақшаңызды қосайық.\n\n**Оны қалай атаймыз?**\n_Мысалдар: Kaspi, Қолма-қол, Halyk, Депозит_",
        "ASK_ACC_BAL": "💵 **Бастапқы капитал**\n\nОсы шоттың ағымдағы балансын көрсетіңіз. Бұл сіздің қаржылық есебіңіздің бастау нүктесі болады.\n\nСоманы **тек цифрмен** жіберіңіз (мысалы, `350000` немесе `0`):",
        "ASK_ADD_MORE": "✅ **Шот сәтті қосылды және жұмысқа дайын!**\n\nҚазір қосқыңыз келетін басқа да шоттарыңыз, карталарыңыз немесе қолма-қол ақшаңыз бар ма? Неғұрлым дәл болса, бот сіздің қаржылық жағдайыңызды соғұрлым жақсы түсінеді.",
        "ASK_DAILY": "📊 **3-қадам (барлығы 3): Сіздің қаржылық радарыңыз**\n\nТабысты адамдар күн сайын қорытынды жасайды. Бот сізге әдемі кешкі жиынтықты жібере алады:\n🟢 Күндік таза кірісіңіз\n🔴 Шығыстарыңыз бен ең көп жұмсалған санаттар\n🔥 Бюджетті жүргізудің үздіксіз сериясы\n\nКүнделікті есепті қосамыз ба?",
        "ASK_DAILY_TIME": "⏰ **Күнделікті есеп үшін оңтайлы уақыт**\n\nКүн қорытындысын көруге ыңғайлы уақытты таңдаңыз немесе `HH:MM` форматында өз уақытыңызды енгізіңіз:",
        "DONE": "👑 **Құттықтаймыз! Негізгі баптау аяқталды.**\n\nСіз ақшаңызды басқаруға бағытталған алғашқы және ең маңызды қадамды жасадыңыз.\n\n**Операцияны 1 рет басу арқылы қалай енгізуге болады:**\nБотқа кез келген мәтінді жіберіңіз, мысалы: `1500 такси` немесе `5000 тамақ` — бот бәрін өзі түсінеді!\n\nБоттың барлық мүмкіндіктері ашық және дайын. Бастайық!",
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
