from html import escape

from states import EnrollStates, MasterStates
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID, services_ru


from database import add_master_db, get_all_masters_db, delete_master_db, update_enroll_status_db

admin_router = Router()

# ================= ПАНЕЛЬ АДМИНИСТРАТОРА =================

@admin_router.message(F.text == 'Управление мастерами')
async def admin_masters_menu(message: Message):
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    kb = [
        [InlineKeyboardButton(text="➕ Добавить мастера", callback_data="admin_add_master")],
        [InlineKeyboardButton(text="❌ Удалить мастера", callback_data="admin_select_delete_master")],
        [InlineKeyboardButton(text="📋 Список мастеров", callback_data="admin_list_masters")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
    await message.answer("🛠 Панель управления мастерами:", reply_markup=keyboard)


@admin_router.callback_query(F.data == "admin_add_master")
async def admin_add_master_click(callback: CallbackQuery, state: FSMContext):
    await state.set_state(MasterStates.waiting_for_doing)
    kb = [
        [InlineKeyboardButton(text="💅 Маникюр", callback_data="admin_add_master_manicure")],
        [InlineKeyboardButton(text="👣 Педикюр", callback_data="admin_add_master_pedicure")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adding")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)

    if isinstance(callback.message, Message):
        await callback.message.edit_text("Шаг 1: К какой услуге относится новый мастер?", reply_markup=keyboard)
    await callback.answer()

@admin_router.callback_query(F.data == "cancel_adding")
async def cancel_adding_click(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text("Добавление прервано.")
    await callback.answer("Отменено")



@admin_router.callback_query(MasterStates.waiting_for_doing, F.data.startswith("admin_add_master_"))
async def process_master_doing(callback: CallbackQuery, state: FSMContext):
    if not callback.data:
        await callback.answer("Ошибка: данные кнопки не найдены.", show_alert=True)
        return

    # Из "admin_add_master_manicure" split("_")[3] вытащит "manicure"
    selected_doing = callback.data.split("_")[3]

    # Сохраняем услугу в память FSM
    await state.update_data(doing=selected_doing)

    # Переводим админа на шаг ожидания текста с именем
    await state.set_state(MasterStates.waiting_for_name)
    kb = [
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_adding")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            text=f"Вы выбрали направление: {services_ru.get(selected_doing)}.\n\n"
                 f"Шаг 2: Напишите в ответном сообщении Имя и Фамилию мастера (на русском):", reply_markup=keyboard
        )
    await callback.answer()


@admin_router.message(MasterStates.waiting_for_name, F.text)
async def admin_save_master_final(message: Message, state: FSMContext):
    if not message.from_user or message.from_user.id != ADMIN_ID:  # Твой ADMIN_ID
        return

    if not message.text:
        return
    master_name = message.text.strip()

    # Достаем из памяти то направление, которое админ выбрал кнопкой на Шаге 1
    user_data = await state.get_data()
    selected_doing = user_data.get("doing")
    if not selected_doing:
        await message.answer("⚠️ Ошибка: направление не выбрано. Начните заново.")
        await state.clear()
        return

    try:
        # 🔥 Передаем в функцию сразу оба значения, чтобы они легли в ОДНУ строчку таблицы
        await add_master_db(name=master_name, doing=selected_doing)

        await message.answer(
            f"✅ Успешно!\n"
            f"Мастер «{master_name}» добавлен в базу данных на направление: {services_ru.get(selected_doing)}."
        )
    except Exception as e:  # noqa: BLE001
        await message.answer("⚠️ Ошибка: Возможно, мастер с таким именем уже существует.")
        print(f"Ошибка при добавлении: {e}")

    await state.clear()



@admin_router.message(EnrollStates.admin_waiting_for_master_name, F.text)
async def admin_save_master(message: Message, state: FSMContext):
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return

    if not message.text:
        return
    master_name = message.text.strip()

    user_data = await state.get_data()
    selected_doing = user_data.get("doing")
    if not selected_doing:
        await message.answer("⚠️ Ошибка: направление не выбрано. Начните заново.")
        await state.clear()
        return

    try:
        # 🔥 Вызываем готовую функцию вместо прямого SQL-запроса
        await add_master_db(name=master_name, doing=selected_doing)
        await message.answer(f"✅ Мастер «{master_name}» успешно добавлен в базу и доступен для записи!")
    except Exception as e:  # noqa: BLE001
        print(f"Ошибка при добавлении мастера: {e}")
        await message.answer("⚠️ Такой мастер уже есть в базе данных.")

    await state.clear()


@admin_router.callback_query(F.data == "admin_list_masters")
async def admin_list_masters(callback: CallbackQuery):
    if not callback.from_user or callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    rows = await get_all_masters_db()
    if not rows:
        if isinstance(callback.message, Message):
            await callback.message.edit_text("📭 В базе данных пока нет ни одного мастера.",
                                             reply_markup=callback.message.reply_markup)
        await callback.answer()
        return

    text = "📋 Действующие мастера в базе:\n\n"

    for i, row in enumerate(rows, 1):
        master_name = row[1]  # ⚠️ Индекс 1 — это имя мастера
        master_doing = row[2]  # ⚠️ Индекс 2 — это его услуга ('manicure' или 'pedicure')

        doing_ru = services_ru.get(master_doing, master_doing)
        text += f"{i}. {master_name} — Направление: {doing_ru}\n"

    if isinstance(callback.message, Message):
        await callback.message.edit_text(text=text, reply_markup=callback.message.reply_markup)
    await callback.answer()


@admin_router.callback_query(F.data == "admin_select_delete_master")
async def admin_select_delete_master(callback: CallbackQuery):
    if not callback.from_user or callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    kb = []
    # 🔥 Вызываем готовую функцию
    masters_rows = await get_all_masters_db()

    for row in masters_rows:
        master_id = row[0]
        master_name = row[1]
        kb.append([InlineKeyboardButton(text=f"🗑 {master_name}", callback_data=f"admin_del_{master_id}")])

    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="cancel_enroll")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)

    if not masters_rows:
        if isinstance(callback.message, Message):
            await callback.message.edit_text("📭 В базе пока нет мастеров для удаления.", reply_markup=keyboard)
        await callback.answer()
        return

    if isinstance(callback.message, Message):
        await callback.message.edit_text("❌ Нажмите на мастера, которого хотите УДАЛИТЬ из базы:", reply_markup=keyboard)
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_del_"))
async def admin_delete_master_confirm(callback: CallbackQuery):
    if not callback.from_user or callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return

    if not callback.data:
        await callback.answer("Ошибка: данные кнопки не найдены.", show_alert=True)
        return

    master_id_str = callback.data.removeprefix("admin_del_")
    if not master_id_str.isdigit():
        await callback.answer("Ошибка: неверный ID мастера.", show_alert=True)
        return

    master_id = int(master_id_str)

    # 🔥 Функция сама удалит и вернет нам имя удаленного мастера для отчета
    master_name = await delete_master_db(master_id)

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"✅ Мастер «{master_name}» успешно удален из базы данных и больше не отображается у клиентов.")
    await callback.answer()


# ================= ОБРАБОТКА НАЖАТИЙ В РАБОЧЕЙ ГРУППЕ =================

@admin_router.callback_query(F.data.startswith("group_accept_"))
async def group_accept_callback(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("Ошибка: данные кнопки не найдены.", show_alert=True)
        return

    enroll_id_str = callback.data.removeprefix("group_accept_")
    if not enroll_id_str.isdigit():
        await callback.answer("Ошибка: неверный ID записи.", show_alert=True)
        return

    enroll_id = int(enroll_id_str)

    # 🔥 Вызываем функцию обновления статуса, она сама вернет нужную строку с данными
    row = await update_enroll_status_db(enroll_id, 'confirmed')

    if not row:
        await callback.answer("⚠️ Запись не найдена в базе данных.", show_alert=True)
        return

    # Твоя правильная логика с индексами из кортежа, который вернула функция
    client_id = row[0]
    date_db = row[1]
    master_db = row[2]
    choise_db = row[3]  # noqa: spell

    service_name = services_ru.get(choise_db, choise_db)

    master_who = escape(callback.from_user.first_name or "мастер")
    if isinstance(callback.message, Message):
        message_text = callback.message.text or ""
        await callback.message.edit_text(
            text=escape(message_text) + f"\n\n🟢 <b>Принято мастером:</b> {master_who}",
            reply_markup=None,
            parse_mode="HTML",
        )
    await callback.answer("Запись подтверждена")

    if callback.bot:
        assert callback.bot is not None
        bot = callback.bot
        try:
            await bot.send_message(
                chat_id=client_id,
                text=(
                    f"🥳 <b>Отличные новости! Ваша запись подтверждена!</b>\n\n"
                    f"💅 Услуга: {escape(str(service_name))}\n"
                    f"👤 Мастер: {escape(str(master_db))}\n"
                    f"📅 Время: {escape(str(date_db))}\n\n"
                    f"Ждем вас в назначенное время! Если планы изменятся, пожалуйста, отмените запись через меню."
                ),
                parse_mode="HTML",
            )
        except Exception as e:  # noqa: BLE001
            print(f"Не удалось написать клиенту в личку: {e}")


@admin_router.callback_query(F.data.startswith("group_reject_"))
async def group_reject_callback(callback: CallbackQuery):
    if not callback.data:
        await callback.answer("Ошибка: данные кнопки не найдены.", show_alert=True)
        return

    enroll_id_str = callback.data.removeprefix("group_reject_")
    if not enroll_id_str.isdigit():
        await callback.answer("Ошибка: неверный ID записи.", show_alert=True)
        return

    enroll_id = int(enroll_id_str)

    # 🔥 Вызываем функцию
    row = await update_enroll_status_db(enroll_id, 'rejected')

    if not row:
        await callback.answer("⚠️ Запись не найдена в базе данных.", show_alert=True)
        return

    client_id = row[0]
    date_db = row[1]
    master_db = row[2]
    choise_db = row[3]  # noqa: spell

    service_name = services_ru.get(choise_db, choise_db)

    master_who = escape(callback.from_user.first_name or "мастер")
    if isinstance(callback.message, Message):
        message_text = callback.message.text or ""
        await callback.message.edit_text(
            text=escape(message_text) + f"\n\n🔴 <b>Отклонено мастером:</b> {master_who}",
            reply_markup=None,
            parse_mode="HTML",
        )
    await callback.answer("Запись отклонена")

    if callback.bot:
        assert callback.bot is not None
        bot = callback.bot
        try:
            await bot.send_message(
                chat_id=client_id,
                text=(
                    f"😔 <b>К сожалению, ваша запись была отклонена мастером.</b>\n\n"
                    f"💅 Услуга: {escape(str(service_name))}\n"
                    f"👤 Мастер: {escape(str(master_db))}\n"
                    f"📅 Время: {escape(str(date_db))}\n\n"
                    f"Попробуйте выбрать другое время или другого мастера."
                ),
                parse_mode="HTML",
            )
        except Exception as e:  # noqa: BLE001
            print(f"Не удалось написать клиенту в личку: {e}")

