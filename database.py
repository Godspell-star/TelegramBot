import aiosqlite

DB_NAME = 'enroll.db'


# Инициализация всех таблиц при старте бота
async def init_enroll_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица записей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS enroll (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                master TEXT,
                choise TEXT,
                status TEXT DEFAULT 'waiting'
            )
        ''')
        # Таблица профилей пользователей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                phone TEXT,
                missed_appointments INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0
            )
        ''')
        # Таблица мастеров (с полем doing)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS masters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                doing TEXT
            )
        ''')
        await db.commit()


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С МАСТЕРАМИ ---

async def add_master_db(name: str, doing: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO masters (name, doing) VALUES (?, ?)", (name, doing))
        await db.commit()


async def get_all_masters_db(doing: str | None = None):
    async with aiosqlite.connect(DB_NAME) as db:
        if doing:
            # Запрос для клиента: фильтруем по услуге
            async with db.execute("SELECT id, name, doing FROM masters WHERE doing = ?", (doing,)) as cursor:
                return await cursor.fetchall()
        else:
            # Запрос для админа: забираем всех мастеров
            async with db.execute("SELECT id, name, doing FROM masters") as cursor:
                return await cursor.fetchall()


async def get_master_by_id_db(master_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT id, name, doing FROM masters WHERE id = ?",
            (master_id,),
        ) as cursor:
            return await cursor.fetchone()


async def delete_master_db(master_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT name FROM masters WHERE id = ?", (master_id,)) as cursor:
            row = await cursor.fetchone()
            master_name = row[0] if row else "Неизвестный мастер"
        await db.execute("DELETE FROM masters WHERE id = ?", (master_id,))
        await db.commit()
        return master_name


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С КЛИЕНТАМИ И ЗАПИСЯМИ ---

async def check_user_status_db(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT is_banned, missed_appointments FROM users WHERE user_id = ?",
                              (user_id,)) as cursor:
            return await cursor.fetchone()


async def register_user_db(user_id: int, name: str, phone: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO users (user_id, name, phone) VALUES (?, ?, ?)", (user_id, name, phone))
        await db.commit()


async def add_enroll_db(user_id: int, date: str, master: str, choise: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT name, phone FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_info = await cursor.fetchone()

        cursor = await db.execute(
            "INSERT INTO enroll (user_id, date, master, choise, status) VALUES (?, ?, ?, ?, 'waiting')",
            (user_id, date, master, choise)
        )
        await db.commit()
        return cursor.lastrowid, user_info


async def get_user_enrolls_db(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, date, master, choise FROM enroll WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchall()


async def update_enroll_status_db(enroll_id: int, status: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE enroll SET status = ? WHERE id = ?", (status, enroll_id))
        await db.commit()
        async with db.execute("SELECT user_id, date, master, choise FROM enroll WHERE id = ?", (enroll_id,)) as cursor:
            return await cursor.fetchone()


async def delete_enroll_db(enroll_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM enroll WHERE id = ?", (enroll_id,))
        await db.commit()