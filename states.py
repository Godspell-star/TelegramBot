from aiogram.fsm.state import State, StatesGroup

class EnrollStates(StatesGroup):
    # 🚀 Новые шаги для регистрации:
    waiting_for_reg_name = State()
    waiting_for_reg_phone = State()

    # Твои старые шаги записи:
    waiting_for_service = State()
    waiting_for_master = State()
    waiting_for_time_slot = State()
    waiting_for_exact_time = State()
    waiting_for_delete = State()
    admin_waiting_for_master_name = State()

class MasterStates(StatesGroup):
    waiting_for_doing = State() # Шаг 1: Выбор услуги мастера
    waiting_for_name = State()