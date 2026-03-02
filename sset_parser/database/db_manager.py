import aiosqlite

DB_PATH = "data/main_db.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            api_id INTEGER,
            api_hash TEXT,
            phone TEXT,
            pos_prompt TEXT DEFAULT 'работа, заказ',
            neg_prompt TEXT DEFAULT 'скам, реклама',
            is_active INTEGER DEFAULT 0
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS user_chats (
            user_id INTEGER,
            chat_username TEXT,
            PRIMARY KEY (user_id, chat_username)
        )""")
        await db.commit()

async def get_active_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE is_active = 1") as cursor:
            return await cursor.fetchall()