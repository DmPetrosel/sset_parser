from telethon import TelegramClient, events
from sqlalchemy import select, delete
from database.models import async_session, User, MonitoredChat
from core.ai_handler import analyze_text

class ClientManager:
    def __init__(self):
        self.clients = {}

    async def add_and_start_client(self, user_id, api_id, api_hash):
        client = TelegramClient(f"data/sessions/{user_id}", api_id, api_hash)
        await client.connect()
        if await client.is_user_authorized():
            self.clients[user_id] = client
            self.register_handlers(client, user_id)
            await client.start()
            return True
        return False

    def register_handlers(self, client, user_id):
        # Хендлер для управления (команды в Saved Messages)
        @client.on(events.NewMessage(incoming=False, chats='me'))
        async def commander(event):
            text = event.raw_text.lower()
            if text.startswith(".add"):
                chat_name = text.replace(".add", "").strip().replace("@", "")
                async with async_session() as session:
                    session.add(MonitoredChat(user_id=user_id, chat_username=chat_name))
                    await session.commit()
                await event.edit(f"✅ Чат **@{chat_name}** добавлен в мониторинг.")

            elif text == ".status":
                async with async_session() as session:
                    res = await session.execute(select(MonitoredChat).where(MonitoredChat.user_id == user_id))
                    chats = [c.chat_username for c in res.scalars().all()]
                await event.edit(f"📊 **Мониторинг:**\n" + "\n".join([f"• @{c}" for c in chats]) if chats else "Список пуст")

        # Хендлер для парсинга сообщений в группах
        @client.on(events.NewMessage)
        async def parser(event):
            if not event.text or event.is_private: return
            
            chat = await event.get_chat()
            username = getattr(chat, 'username', None)
            if not username: return

            async with async_session() as session:
                # Проверка: следит ли юзер за этим чатом
                stmt = select(MonitoredChat).where(
                    MonitoredChat.user_id == user_id, 
                    MonitoredChat.chat_username == username.lower()
                )
                if not (await session.execute(stmt)).scalar(): return
                
                # Получаем промпты
                user = (await session.execute(select(User).where(User.user_id == user_id))).scalar()

            if await analyze_text(event.text, user.pos_prompt, user.neg_prompt):
                link = f"https://t.me/{username}/{event.id}"
                await client.send_message('me', f"🎯 **Найдено!**\n\n{event.text[:500]}\n\n🔗 [К сообщению]({link})")