from aiogram.fsm.state import StatesGroup, State

class RegisterState(StatesGroup):
    waiting_for_username = State()
