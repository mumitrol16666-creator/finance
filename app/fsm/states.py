from aiogram.fsm.state import StatesGroup, State

class TelegramOnboarding(StatesGroup):
    select_auth_type = State()
    tg_link_login = State()
    tg_link_password = State()
    tg_reg_name = State()
    tg_reg_login = State()
    tg_reg_password = State()
    ai_survey_invite = State()
    ai_survey_q1 = State()
    ai_survey_q2 = State()
    ai_survey_q3 = State()
    ai_survey_q4 = State()
    waiting_legacy_password = State()


class ExpenseFlow(StatesGroup):
    amount = State()
    account = State()
    category = State()
    need_note = State()
    note = State()
    confirm = State()
    confirm_overdraft = State()
    add_category = State()


class IncomeFlow(StatesGroup):
    amount = State()
    account = State()
    category = State()
    need_note = State()
    note = State()
    confirm = State()
    add_category = State()
    piggy_suggest = State()
    piggy_amount = State()

class TransferFlow(StatesGroup):
    amount = State()
    from_account = State()
    to_account = State()
    need_note = State()
    note = State()
    confirm = State()
    confirm_overdraft = State()

class SettingsFlow(StatesGroup):
    daily_report_time = State()

    rename_pick = State()
    rename_new = State()
    balance_pick = State()
    balance_new = State()
    archive_pick = State()
    archived_pick = State()
    add_name = State()
    add_balance = State()
    add_currency = State()
    add_type = State()

    # Transaction Editing Flow States
    tx_edit_amount = State()
    tx_edit_note = State()


class QuickAddFlow(StatesGroup):
    draft = State()
    pick_type = State()
    edit_amount = State()
    new_cat_name = State()
    batch_confirm = State()

class CategoriesFlow(StatesGroup):
    add_name = State()
    rename = State()
    emoji = State()

class BudgetFlow(StatesGroup):
    pick_category = State()
    enter_amount = State()
    confirm = State()


class AiConsultantFlow(StatesGroup):
    waiting_goal = State()
    waiting_question = State()
    waiting_context_note = State()
    ai_chatting = State()


class RecurringExpenseFlow(StatesGroup):
    title = State()
    amount = State()
    category = State()
    account = State()
    day = State()
    comment = State()


class RecurringIncomeFlow(StatesGroup):
    title = State()
    amount = State()
    category = State()
    account = State()
    day = State()
    comment = State()


class PlannedFlow(StatesGroup):
    kind = State()
    title = State()
    amount = State()
    importance = State()
    category = State()
    account = State()
    date = State()
    comment = State()
    move_date = State()
