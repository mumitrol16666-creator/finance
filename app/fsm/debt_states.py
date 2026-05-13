
from aiogram.fsm.state import State, StatesGroup


class DebtAdd(StatesGroup):
    direction = State()
    dtype = State()
    title = State()
    remaining = State()
    payment = State()
    custom_due_date = State()
    confirm = State()


class DebtPay(StatesGroup):
    amount = State()
