import asyncio
from html import escape

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import ADMIN_ID, GROUP_CHAT_ID

from dotenv import load_dotenv
load_dotenv()
import os

# Импортируем ваши роутеры для записи
from admin import admin_router
from client_enroll import client_menu_keyboard, client_router
from database import init_enroll_db

dp = Dispatcher()
# Этот роутер подключается первым, чтобы /start срабатывал даже посреди записи
commands_router = Router()
main_router = Router()


# --- ХЭНДЛЕРЫ ДЛЯ КОМАНД ---

@commands_router.message(CommandStart())
@commands_router.message(F.text == "Назад!")
async def start_command(message: Message, state: FSMContext):
    await state.clear()

    if message.from_user is None or message.bot is None:
        return

    user_name = message.from_user.first_name
    user_id = message.from_user.id

    if user_id == ADMIN_ID:
        kb = [
            [
                KeyboardButton(text="Управление мастерами")
            ]
        ]
        keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
        await message.answer("Привет, Админ! Вот ваши кнопки:", reply_markup=keyboard)
    else:
        await message.answer(
            f"Привет, {user_name}! Выбери команду на кнопках внизу:",
            reply_markup=client_menu_keyboard(),
        )


@commands_router.message(F.text == '/info')
async def info_command(message: Message):
    if message.from_user is None:
        return
    if message.bot is None:
        return

    assert message.bot is not None
    bot = message.bot
    bot_info = await bot.get_me()
    bot_name = bot_info.first_name or "Бот"
    user_id = message.from_user.id

    admin_name: str = "Администратор"

    try:
        admin_chat = await bot.get_chat(ADMIN_ID)
        if admin_chat is not None:
            if admin_chat.first_name:
                admin_name = admin_chat.first_name
            if admin_chat.username:
                admin_name += f" (@{admin_chat.username})"
    except Exception as e:  # noqa: BLE001
        admin_name = "Администратор"
        print(f"Предупреждение при получении чата админа: {e}")

    await message.answer(
        f"ℹ️ Это мой первый бот для работы как пример, в котором я буду учиться делать сложные вещи\n\n"
        f"🤖 Меня зовут: {escape(bot_name)}\n"
        f"👤 <b>Создатель:</b> {escape(admin_name)}\n"
        f"🆔 Мое айди: {ADMIN_ID}\n"
        f"🆔 Ваше айди: {user_id}",
        parse_mode=ParseMode.HTML,
    )


# Эхо-хэндлер для обработки ВСЕГО ОСТАЛЬНОГО
@main_router.message()
async def echo_handler(message: Message):
    await message.answer("Я тебя не понимаю, попробуй написать /start или нажать кнопки внизу.")


# --- ЗАПУСК БОТА ---

async def main():
    token = os.getenv("BOT_TOKEN")

    if not token:
        raise ValueError("No token provided")

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    print("Инициализация базы данных и создание таблиц...")
    await init_enroll_db()

    dp.include_router(commands_router)
    dp.include_router(client_router)
    dp.include_router(admin_router)
    dp.include_router(main_router)

    print("Starting bot...")
    try:
        try:
            await bot.delete_webhook(drop_pending_updates=True)
        except Exception as e:  # noqa: BLE001
            print(f"Предупреждение при удалении вебхука: {e}")
            await bot.delete_webhook()

        await dp.start_polling(bot)
    finally:
        if bot.session:
            await bot.session.close()
        print("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
