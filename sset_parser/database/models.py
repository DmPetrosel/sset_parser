from sqlalchemy import Column, Integer, String, BigInteger, ForeignKey
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    user_id = Column(BigInteger, primary_key=True)
    api_id = Column(Integer)     # Индивидуальный ID
    api_hash = Column(String)    # Индивидуальный Hash
    phone = Column(String)
    pos_prompt = Column(String, default="заказ, работа")
    neg_prompt = Column(String, default="реклама, скам")
    common_prompt = Column(String, default="Подбирай подходящие по смыслу")
    stop_words = Column(String, default="")
    min_keywords = Column(Integer, default=2)

class MonitoredChat(Base):
    __tablename__ = "monitored_chats"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"))
    chat_username = Column(String, nullable=False)

ENGINE = create_async_engine("sqlite+aiosqlite:///data/main_db.db")
async_session = async_sessionmaker(ENGINE, expire_on_commit=False)

async def _migrate(conn):
    """Добавляет недостающие колонки в существующие таблицы."""
    def sync_migrate(sync_conn):
        for table in Base.metadata.sorted_tables:
            result = sync_conn.execute(
                __import__("sqlalchemy").text(f"PRAGMA table_info({table.name})")
            )
            existing = {row[1] for row in result}
            for col in table.columns:
                if col.name not in existing:
                    col_type = col.type.compile(dialect=sync_conn.dialect)
                    default = ""
                    if col.default is not None and col.default.is_scalar:
                        val = col.default.arg
                        default = f" DEFAULT {repr(val)}" if isinstance(val, str) else f" DEFAULT {val}"
                    sync_conn.execute(
                        __import__("sqlalchemy").text(
                            f"ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}{default}"
                        )
                    )
    await conn.run_sync(sync_migrate)

async def init_db():
    async with ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate(conn)