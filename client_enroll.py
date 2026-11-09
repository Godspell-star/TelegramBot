from html import escape

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime

from config import GROUP_CHAT_ID, services_ru

# ИМПОРТ СОСТОЯНИЙ (из файла states.py в корне)
from states import EnrollStates

# ИМПОРТ ФУНКЦИЙ БАЗЫ ДАННЫХ (из файла database.py в корне)
from database import (
    check_user_status_db,
    register_user_db,
    get_all_masters_db,
    get_master_by_id_db,
    add_enroll_db,
    get_user_enrolls_db,
    delete_enroll_db
)

# СОЗДАНИЕ РОУТЕРА (Именно его бот не видит!)
client_router = Router()


def client_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="Записаться"),
            KeyboardButton(text="Ваши записи"),
            KeyboardButton(text="Отменить запись"),
        ]],
        resize_keyboard=True,
    )


def masters_keyboard(masters_rows) -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text=row[1], callback_data=f"master_{row[0]}")]
        for row in masters_rows
    ]
    kb.append([InlineKeyboardButton(text="⬅️ Назад к услугам", callback_data="back_to_services")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ================= ШАГ 1: НАЖАТИЕ "ЗАПИСАТЬСЯ" =================

@client_router.message(F.text == 'Записаться')
async def enroll_menu(message: Message, state: FSMContext):
    if not message.from_user:
        return
    user_id = message.from_user.id

    # 🔥 Используем импортированную функцию проверки статуса
    user_row = await check_user_status_db(user_id)

    if user_row:
        is_banned = user_row[0]
        missed_appointments = user_row[1]
        if is_banned == 1:
            await message.answer(f"❌ Доступ заблокирован. Вы не явились на запись {missed_appointments} раза.")
            return

    # Если профиля нет в базе — отправляем на регистрацию
    if not user_row:
        await state.set_state(EnrollStates.waiting_for_reg_name)
        await message.answer(
            "👋 Похоже, вы у нас впервые! Давайте зарегистрируемся.\n\nВведите ваше Имя и Фамилию:"
        )
        return

    # Если профиль есть — сразу открываем выбор услуг
    await state.set_state(EnrollStates.waiting_for_service) 
    kb = [
        [InlineKeyboardButton(text="Маникюр", callback_data="service_manicure")],
        [InlineKeyboardButton(text="Педикюр", callback_data="service_pedicure")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_enroll")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
    await message.answer("Шаг 1: Выберите услугу:", reply_markup=keyboard)


# ================= РЕГИСТРАЦИЯ: СБОР ИМЕНИ И ТЕЛЕФОНА =================

@client_router.message(EnrollStates.waiting_for_reg_name, F.text)
async def reg_name(message: Message, state: FSMContext):
    if not message.text:
        return
    await state.update_data(reg_name=message.text.strip())
    await state.set_state(EnrollStates.waiting_for_reg_phone)

    kb = [[KeyboardButton(text="📱 Поделиться телефоном", request_contact=True)]]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

    await message.answer(
        "Отлично! Теперь нажмите кнопку внизу чата, чтобы отправить свой номер телефона:",
        reply_markup=keyboard
    )


@client_router.message(EnrollStates.waiting_for_reg_phone, F.contact)
async def reg_phone(message: Message, state: FSMContext):
    if not message.from_user or not message.contact:
        return

    # Кнопка «Поделиться телефоном» присылает контакт самого пользователя.
    # Пересланный чужой контакт сюда не пускаем.
    if message.contact.user_id != message.from_user.id:
        await message.answer("Нажмите кнопку «Поделиться телефоном», чтобы отправить свой номер.")
        return

    user_data = await state.get_data()
    name = user_data.get("reg_name")
    if not name:
        await message.answer("⚠️ Ошибка: имя не введено. Начните заново.")
        await state.clear()
        return
    phone = message.contact.phone_number
    user_id = message.from_user.id

    # 🔥 Используем импортированную функцию регистрации
    await register_user_db(user_id, name, phone)

    await message.answer(
        "🎉 Регистрация успешно завершена! Теперь вы можете записываться.",
        reply_markup=client_menu_keyboard(),
    )

    await state.set_state(EnrollStates.waiting_for_service)
    kb = [
        [InlineKeyboardButton(text="Маникюр", callback_data="service_manicure")],
        [InlineKeyboardButton(text="Педикюр", callback_data="service_pedicure")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_enroll")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
    await message.answer("Шаг 1: Выберите услугу:", reply_markup=keyboard)


# ================= ШАГ 2: ВЫБОР ДИНАМИЧЕСКОГО МАСТЕРА =================

@client_router.callback_query(EnrollStates.waiting_for_service, F.data.startswith("service_"))
async def process_service(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        await callback.answer("Ошибка: данные кнопки не найдены.", show_alert=True)
        return

    # Из "service_manicure" берем "manicure"
    selected_service = callback.data.split("_")[1]
    await state.update_data(choise=selected_service)
    await state.set_state(EnrollStates.waiting_for_master)

    # 🔥 Передаем выбранную услугу в функцию базы данных!
    masters_rows = await get_all_masters_db(doing=selected_service)

    if not masters_rows:
        if isinstance(callback.message, Message):
            await callback.message.edit_text(
                text="Извините, сейчас нет доступных мастеров для этой услуги.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_services")]])
            )
        await callback.answer()
        return

    keyboard = masters_keyboard(masters_rows)

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text=f"Вы выбрали: {services_ru.get(selected_service, selected_service)}.\n\nШаг 2: Выберите мастера:",
            reply_markup=keyboard
        )
    await callback.answer()


@client_router.callback_query(EnrollStates.waiting_for_master, F.data == "back_to_services")
async def back_to_services_handler(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EnrollStates.waiting_for_service)
    kb = [
        [InlineKeyboardButton(text="Маникюр", callback_data="service_manicure")],
        [InlineKeyboardButton(text="Педикюр", callback_data="service_pedicure")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_enroll")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
    if isinstance(callback.message, Message):
        await callback.message.edit_text("Шаг 1: Выберите услугу:", reply_markup=keyboard)
    await callback.answer()


# ================= ШАГ 3: ВЫБОР ПРОМЕЖУТКА ВРЕМЕНИ =================

@client_router.callback_query(EnrollStates.waiting_for_master, F.data.startswith("master_"))
async def process_master(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        await callback.answer("Ошибка: данные кнопки не найдены.", show_alert=True)
        return

    raw_id = callback.data.removeprefix("master_")
    if not raw_id.isdigit():
        await callback.answer("Эта кнопка устарела. Начните запись заново.", show_alert=True)
        return

    master_row = await get_master_by_id_db(int(raw_id))
    if not master_row:
        await callback.answer("Этого мастера уже нет. Выберите другого.", show_alert=True)
        return

    selected_master = master_row[1]
    await state.update_data(master=selected_master)
    await state.set_state(EnrollStates.waiting_for_time_slot)

    kb = [
        [InlineKeyboardButton(text="🌅 Утро (9:00 - 13:00)", callback_data="slot_morning")],
        [InlineKeyboardButton(text="☀️ День (13:00 - 17:00)", callback_data="slot_afternoon")],
        [InlineKeyboardButton(text="🌌 Вечер (17:00 - 21:00)", callback_data="slot_evening")],
        [InlineKeyboardButton(text="⬅️ Назад к мастерам", callback_data="back_to_masters")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text=f"Выбранный мастер: {selected_master}.\n\nШаг 3: Выберите удобное время дня:",
            reply_markup=keyboard
        )
    await callback.answer()


# НАЗАД К МАСТЕРАМ (Нажимается на шаге выбора промежутка дня)
@client_router.callback_query(EnrollStates.waiting_for_time_slot, F.data == "back_to_masters")
async def back_to_masters_handler(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EnrollStates.waiting_for_master)

    user_data = await state.get_data()
    selected_doing = user_data.get("choise")  # noqa: spell
    if selected_doing:
        masters_rows = await get_all_masters_db(doing=selected_doing)
    else:
        masters_rows = []
    keyboard = masters_keyboard(masters_rows)

    if isinstance(callback.message, Message):
        await callback.message.edit_text("Шаг 2: Выберите мастера:", reply_markup=keyboard)
    await callback.answer()


# ================= ШАГ 4: ВЫБОР ТОЧНОГО ВРЕМЕНИ =================

@client_router.callback_query(EnrollStates.waiting_for_time_slot, F.data.startswith("slot_"))
async def process_time_slot(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        await callback.answer("Ошибка: данные кнопки не найдены.", show_alert=True)
        return

    slot = callback.data.split("_")[1]
    await state.update_data(time_slot=slot)
    await state.set_state(EnrollStates.waiting_for_exact_time)

    kb = []
    if slot == "morning":
        kb = [
            [InlineKeyboardButton(text="09:00", callback_data="time_09:00")],
            [InlineKeyboardButton(text="10:00", callback_data="time_10:00")],
            [InlineKeyboardButton(text="11:00", callback_data="time_11:00")]
        ]
    elif slot == "afternoon":
        kb = [
            [InlineKeyboardButton(text="13:00", callback_data="time_13:00")],
            [InlineKeyboardButton(text="14:00", callback_data="time_14:00")],
            [InlineKeyboardButton(text="15:00", callback_data="time_15:00")]
        ]
    elif slot == "evening":
        kb = [
            [InlineKeyboardButton(text="17:00", callback_data="time_17:00")],
            [InlineKeyboardButton(text="18:00", callback_data="time_18:00")],
            [InlineKeyboardButton(text="19:00", callback_data="time_19:00")]
        ]

    kb.append([InlineKeyboardButton(text="⬅️ Назад к промежуткам", callback_data="back_to_slots")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)

    slots_ru = {"morning": "Утро", "afternoon": "День", "evening": "Вечер"}
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text=f"Выбранный промежуток: {slots_ru.get(slot)}.\n\nШаг 4: Выберите точное время:",
            reply_markup=keyboard
        )
    await callback.answer()


# НАЗАД К ПРОМЕЖУТКАМ (Нажимается на шаге выбора точного времени)
@client_router.callback_query(EnrollStates.waiting_for_exact_time, F.data == "back_to_slots")
async def back_to_slots_handler(callback: CallbackQuery, state: FSMContext):
    await state.set_state(EnrollStates.waiting_for_time_slot)

    user_data = await state.get_data()
    selected_master = user_data.get("master") or "Мастер"

    kb = [
        [InlineKeyboardButton(text="🌅 Утро (9:00 - 13:00)", callback_data="slot_morning")],
        [InlineKeyboardButton(text="☀️ День (13:00 - 17:00)", callback_data="slot_afternoon")],
        [InlineKeyboardButton(text="🌌 Вечер (17:00 - 21:00)", callback_data="slot_evening")],
        [InlineKeyboardButton(text="⬅️ Назад к мастерам", callback_data="back_to_masters")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text=f"Выбранный мастер: {selected_master}.\n\nШаг 3: Выберите удобное время дня:",
            reply_markup=keyboard
        )
    await callback.answer()


# ================= ШАГ 5: ФИНАЛ — СОХРАНЕНИЕ В БД И УВЕДОМЛЕНИЕ =================

@client_router.callback_query(EnrollStates.waiting_for_exact_time, F.data.startswith("time_"))
async def process_exact_time(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        await callback.answer("Ошибка: данные кнопки не найдены.", show_alert=True)
        return

    exact_time = callback.data.removeprefix("time_")

    user_data = await state.get_data()
    selected_service = user_data.get("choise")  # noqa: spell
    selected_master = user_data.get("master")

    if not selected_service or not selected_master:
        await callback.answer("Ошибка: данные записи потеряны. Начните заново.", show_alert=True)
        await state.clear()
        return

    user_id = callback.from_user.id

    final_date_time = f"{datetime.now().strftime('%d-%m-%Y')} в {exact_time}"

    # 🔥 Функция из database.py делает всю работу с БД и возвращает нужные данные
    enroll_id, user_info = await add_enroll_db(user_id, final_date_time, selected_master, selected_service)

    client_name = user_info[0] if user_info else (callback.from_user.first_name if callback.from_user else "Клиент")
    client_phone = user_info[1] if user_info else "Не указан"

    await state.clear()

    service_name = services_ru.get(selected_service, selected_service)

    # Отвечаем клиенту
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text=f"⏳ Ваша заявка отправлена мастерам на рассмотрение!\n\n"
                 f"💅 Услуга: {service_name}\n"
                 f"👤 Мастер: {selected_master}\n"
                 f"📅 Время: {final_date_time}\n\n"
                 f"Ожидайте подтверждения в чате."
        )
    await callback.answer()

    # Сборка кнопок для группы мастеров
    admin_kb = [
        [
            InlineKeyboardButton(text="✅ Принять", callback_data=f"group_accept_{enroll_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"group_reject_{enroll_id}")
        ]
    ]
    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=admin_kb)

    # Отправляем в группу
    if callback.bot:
        assert callback.bot is not None
        bot = callback.bot
        try:
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=(
                    f"🔔 <b>Заявка на запись №{enroll_id}</b>\n\n"
                    f"👤 <b>Клиент:</b> {escape(str(client_name))}\n"
                    f"📞 <b>Телефон:</b> {escape(str(client_phone))}\n"
                    f"💅 <b>Услуга:</b> {escape(str(service_name))}\n"
                    f"✂️ <b>Мастер:</b> {escape(str(selected_master))}\n"
                    f"📅 <b>Время:</b> {escape(final_date_time)}"
                ),
                reply_markup=admin_keyboard,
                parse_mode="HTML",
            )
        except Exception as e:  # noqa: BLE001
            print(f"Ошибка отправки в группу: {e}")

# ================= 10. КНОПКА ОТМЕНЫ ВСЕГО ПРОЦЕССА ЗАПИСИ =================

@client_router.callback_query(F.data == "cancel_enroll")
async def cancel_enroll_click(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text("Запись прервана.")
    await callback.answer("Отменено")


# ================= ПРОСМОТР ЗАПИСЕЙ КЛИЕНТОМ =================

@client_router.message(F.text == 'Ваши записи')
async def show_enrolls(message: Message):
    if not message.from_user:
        return

    user_id = message.from_user.id

    # 🔥 Используем импортированную функцию из database.py
    rows = await get_user_enrolls_db(user_id)

    if not rows:
        await message.answer("📭 У тебя пока нет активных записей.")
        return


    text_response = "📋 Твои записи:\n\n"

    for row in rows:
        date_db = row[1]    # Индекс 1 — это поле date из таблицы
        master_db = row[2]  # Индекс 2 — это поле master
        choise_db = row[3]  # noqa: spell

        service_name = services_ru.get(choise_db, choise_db)
        text_response += f"📆 {date_db} — Мастер: {master_db} (Услуга: {service_name})\n"

    await message.answer(text_response)


# ================= ОТМЕНА ЗАПИСИ КЛИЕНТОМ =================

@client_router.message(F.text == 'Отменить запись')
async def start_delete_enroll(message: Message, state: FSMContext):
    if not message.from_user:
        return

    user_id = message.from_user.id

    kb = [[InlineKeyboardButton(text="❌ Отмена действия", callback_data="cancel_delete_enroll")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)

    # 🔥 Запрашиваем записи через готовую функцию
    rows = await get_user_enrolls_db(user_id)

    if not rows:
        await message.answer("❌ У вас пока нет записей для отмены.")
        return

    await state.set_state(EnrollStates.waiting_for_delete)


    text_response = "📋 Выберите номер записи, которую хотите отменить:\n\n"
    for i, row in enumerate(rows, 1):
        service_name = services_ru.get(row[3], row[3])
        text_response += f"{i}. 📆 {row[1]} — Мастер: {row[2]} ({service_name})\n"

    await message.answer(text_response, reply_markup=keyboard)


@client_router.callback_query(F.data == "cancel_delete_enroll")
async def cancel_delete_enroll_click(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text("Отмена действия прекращена.")
    await callback.answer("Отменено")


@client_router.message(EnrollStates.waiting_for_delete, F.text)
async def process_delete_enroll(message: Message, state: FSMContext):
    if not message.from_user:
        return

    user_id = message.from_user.id
    user_text = message.text or ""

    if not user_text.isdigit():
        await message.answer("⚠️ Пожалуйста, введите только номер записи (цифру):")
        return

    chosen_index = int(user_text) - 1

    # 🔥 Снова запрашиваем список записей для удаления
    rows = await get_user_enrolls_db(user_id)

    if chosen_index < 0 or chosen_index >= len(rows):
        await message.answer("❌ Записи с таким номером не существует. Попробуйте еще раз:")
        return

    # Разбираем индексы из кортежа, полученного из базы через функцию
    db_id_to_delete = rows[chosen_index][0]
    deleted_date = rows[chosen_index][1]
    deleted_master = rows[chosen_index][2]
    deleted_service = rows[chosen_index][3]

    # 🔥 Вызываем готовую функцию удаления из базы
    await delete_enroll_db(db_id_to_delete)

    service_name = services_ru.get(deleted_service, deleted_service)

    await message.answer(
        f"🗑️ Запись успешно отменена!\n\n"
        f"📆 Было записано на: {deleted_date}\n"
        f"👤 Мастер: {deleted_master}\n"
        f"💅 Услуга: {service_name}"
    )
    await state.clear()