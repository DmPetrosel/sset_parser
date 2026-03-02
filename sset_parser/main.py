import asyncio
import os
from loguru import logger
import sqlite3
import qrcode
from io import BytesIO
from telethon import TelegramClient, events, errors
from sqlalchemy import select
from database.models import init_db, async_session, User
from core.matcher import matches_filter
import config
# Импорт GigaChat
from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole



class ParserApp:
    def __init__(self):
        self.bot = TelegramClient('data/sessions/bot_session', config.MASTER_API_ID, config.MASTER_API_HASH)
        self.user_clients = {}
        self.queue = asyncio.Queue()
        self.giga_client = GigaChat(
    credentials=config.GIGACHAT_CREDENTIALS,
    scope="GIGACHAT_API_B2B", # Для физлиц (Personal)
    # scope="GIGACHAT_API_CORP", # Если у вас бизнес-аккаунт
    verify_ssl_certs=False
)

    async def start(self):
        await init_db()
        await self.bot.start(bot_token=config.BOT_TOKEN)
        logger.info("🤖 Бот-менеджер запущен.")

        self.setup_handlers()

        asyncio.create_task(self.worker())
        
        # Автозапуск существующих сессий
        async with async_session() as session:
            users = (await session.execute(select(User))).scalars().all()
            for u in users:
                asyncio.create_task(self.run_user_parser(u.user_id))

        await self.bot.run_until_disconnected()
    async def clear(self, user_id):
        if user_id in self.user_clients:
            del self.user_clients[user_id]
    def setup_handlers(self):
        # Команда настройки ключевых слов
        @self.bot.on(events.NewMessage(pattern='/settings'))
        async def settings_handler(event):
            await self.clear(event.sender_id)
            uid = event.sender_id
            async with self.bot.conversation(uid, timeout=300, exclusive=False) as conv: 
                try:
                    pros = "не установлены"
                    neg = "не установлены"
                    stop_words = "не установлены"
                    common = "не установлены"
                    min_kw = 2
                    async with async_session() as session:
                        user = await session.get(User, uid)
                        if user:
                          pros = user.pos_prompt
                          neg = user.neg_prompt
                          common = user.common_prompt
                          stop_words = user.stop_words
                          min_kw = user.min_keywords if user.min_keywords is not None else 2
                    await conv.send_message(f"📝 **Шаг 1 из 5**\nВведите ключевые слова через запятую. Вот предыдущие: `{pros}`")
                    pos_msg = await conv.get_response()
                    pos_text = pos_msg.text.strip()

                    await conv.send_message(f"🚫 **Шаг 2 из 5**\nВведите стоп-слова через запятую. Вот предыдущие `{stop_words}`")
                    stop_msg = await conv.get_response()
                    stop_text = stop_msg.text.strip()

                    # await conv.send_message(f"🤚 **Шаг 3 из 5**\nВведите негативный промпт, что не должно быть в сообщениях. Вот предыдущие `{neg}`")
                    # neg_msg = await conv.get_response()
                    # neg_text = neg_msg.text.strip()

                    # await conv.send_message(f"✨ **Шаг 4 из 5**\nВведите общий промпт, по каким критериям подбирать сообщения. Вот предыдущий `{common}`")
                    # common_msg = await conv.get_response()
                    # common = common_msg.text.strip()

                    await conv.send_message(f"🔢 **Шаг 5 из 5**\nСколько ключевых слов должно совпасть, чтобы сообщение попало в обработку? Текущее значение: `{min_kw}`\n(Введите целое число, например: 1, 2, 3)")
                    min_kw_msg = await conv.get_response()
                    try:
                        min_kw_new = int(min_kw_msg.text.strip())
                        if min_kw_new < 1:
                            min_kw_new = 1
                    except ValueError:
                        min_kw_new = min_kw
                        await conv.send_message(f"⚠️ Введено не число, оставляю предыдущее значение: {min_kw}")

                    async with async_session() as session:
                        user = await session.get(User, uid)
                        if user:
                            user.pos_prompt = pos_text
                            # user.neg_prompt = neg_text
                            # user.common_prompt = common
                            user.stop_words = stop_text
                            user.min_keywords = min_kw_new
                            await session.commit()
                        else:
                            await conv.send_message("❌ Ошибка: пользователь не найден в БД. Сначала /login_qr")
                            return
                    await conv.send_message(f"✅ Сохранено!")
                except asyncio.TimeoutError:
                    await self.bot.send_message(uid, "⏰ Время вышло.")

        # Команда проверки статуса
        @self.bot.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            uid = event.sender_id
            is_active = uid in self.user_clients
            await event.respond(f"📊 Статус парсера: {'✅ Активен' if is_active else '❌ Выключен'}")

        # Авторизация через QR
        @self.bot.on(events.NewMessage(pattern='/login_qr'))
        async def qr_login_handler(event):
            uid = event.sender_id
            await self.clear(uid)
            client = TelegramClient(f'data/sessions/user_{uid}', config.MASTER_API_ID, config.MASTER_API_HASH)
            await client.connect()
            qr_login = await client.qr_login()
            
            img = qrcode.make(qr_login.url)
            buf = BytesIO()
            img.save(buf, bitmap_format='png')
            buf.name = "qr.png"
            buf.seek(0)
            await self.bot.send_file(uid, buf, caption="📸 Сканируй QR!", file_name="qr.png")

            try:
                user = await qr_login.wait(60)
            except errors.SessionPasswordNeededError:
                async with self.bot.conversation(uid) as conv:
                    # 1. Сохраняем сообщение бота в переменную
                    question = await conv.send_message("🔐 Введи 2FA пароль:")
                    
                    # 2. Получаем ответ пользователя
                    resp = await conv.get_response()
                    password = resp.text
                    
                    try:
                        # Сначала удаляем сообщения, чтобы пароль не висел в чате ни секунды лишней
                        # Удаляем через клиент бота, так надежнее
                        await self.bot.delete_messages(uid, [question.id, resp.id])
                        
                        # 3. Входим в аккаунт
                        user = await client.sign_in(password=password)
                        
                    except Exception as e:
                        # Если пароль неверный, сообщения всё равно должны быть удалены
                        await self.bot.send_message(uid, f"❌ Ошибка при вводе пароля: {e}")
            
            if user:
                async with async_session() as session:
                    await session.merge(User(user_id=uid, phone=str(user.phone)))
                    await session.commit()
                await self.bot.send_message(uid, f"✅ Вошли как {user.first_name}")

                asyncio.create_task(self.run_user_parser(uid))
    async def worker(self):
        logger.info("🚀 Воркер GigaChat запущен.")
        while True:
            event, user_id, user_data = await self.queue.get()
            
            try:
                # GigaChat более лоялен к частоте запросов, но 0.5-1 сек стоит держать
                await asyncio.sleep(0.5) 
                
                # is_relevant = await self.ask_gigachat(
                #     event.text, 
                #     user_data.pos_prompt, 
                #     user_data.neg_prompt, 
                #     user_data.common_prompt
                # )
                
                if True:
                    await self.send_notification(user_data, event, user_id)

            except Exception as e:
                if "429" in str(e):
                    logger.warning(f"⚠️ Лимит GigaChat! Ждем...")
                    await asyncio.sleep(10)
                    await self.queue.put((event, user_id, user_data))
                else:
                    logger.error(f"Ошибка воркера: {e}")
            finally:
                self.queue.task_done()
                
    async def run_user_parser(self, user_id):
        # Если клиент уже запущен, сначала отключаем его
        if user_id in self.user_clients:
            try:
                await self.user_clients[user_id].disconnect()
            except:
                pass

        # Создаем новый клиент с увеличенным таймаутом для SQLite
        client = TelegramClient(
            f'data/sessions/user_{user_id}', 
            config.MASTER_API_ID, 
            config.MASTER_API_HASH,
            base_logger=logger # Меньше мусора в логах
        )
        
        try:
            # Устанавливаем задержку на попытку записи в БД
            await client.connect()
        except sqlite3.OperationalError:
            logger.error(f"БД заблокирована для {user_id}, ждем...")
            await asyncio.sleep(5)
            await client.connect()

        try:
            await client.connect()
            if not await client.is_user_authorized():
                logger.warning(f"⚠️ Пользователь {user_id} не авторизован.")
                await client.disconnect()
                return

            self.user_clients[user_id] = client
            logger.info(f"📡 Мониторинг для {user_id} активен.")

            @client.on(events.NewMessage)
            async def message_handler(event):
                if event.is_private or not event.text: return
                logger.debug(f"Получено сообщение для {user_id}: «{event.text[:80]}»")

                try:
                    # 1. Получаем настройки
                    async with async_session() as session:
                        user_data = await session.get(User, user_id)
                        if not user_data: return

                    # 2. ФИЛЬТРАЦИЯ (морфология + сигналы заказа)
                    min_kw = user_data.min_keywords if user_data.min_keywords is not None else 2
                    logger.debug(f"Настройки {user_id}: keywords={user_data.pos_prompt!r} stop={user_data.stop_words!r} min={min_kw}")
                    if matches_filter(event.text, user_data.pos_prompt, user_data.stop_words, min_kw):
                        await self.queue.put((event, user_id, user_data))
                        logger.info(f"Сообщение добавлено в очередь для {user_id}: {event.text[:400]}")
                except Exception as e:
                    logger.error(f"Ошибка в message_handler для {user_id}: {e}")

            # Важно: уберите await client.run_until_disconnected() отсюда, 
            # чтобы метод завершился, а клиент остался работать в фоне.
                    # 4. Проверка Mistral AI
                self.user_clients[user_id] = client
            # ВАЖНО: не используем run_until_disconnected здесь, 
            # иначе мы заблокируем создание других клиентов.
            # Просто держим соединение открытым.
            await client.run_until_disconnected()

        except Exception as e:
            logger.error(f"💥 Ошибка в клиенте {user_id}: {e}")
        finally:
            if user_id in self.user_clients:
                del self.user_clients[user_id]
    async def send_notification(self,user_data, event, user_id):
        sender = await event.get_sender()
        chat = await event.get_chat()
        
        # Формируем имя отправителя (username или Имя + Фамилия)
        if sender:
            username = f"@{sender.username}" if getattr(sender, 'username', None) else f"{sender.first_name or ''} {sender.last_name or ''}".strip()
        else:
            username = "Скрытый пользователь"

        # Лог в консоль для проверки
        logger.debug(f"DEBUG: {user_id} видит сообщение от {username} в {getattr(chat, 'title', 'чате')} {event.text[:500]}")

        
        # is_relevant = await self.ask_mistral(event.text, user_data.pos_prompt, user_data.neg_prompt, user_data.common_prompt)
        
        # if is_relevant:
        title = getattr(chat, 'title', 'Чат')
        # Формируем ссылку на сообщение, если у чата есть username
        link = f"https://t.me/{chat.username}/{event.id}" if getattr(chat, 'username', None) else "Закрытая группа"
        try:
        # Отправляем сообщение с данными автора
            await self.bot.send_message(
            user_id, 
            f"🎯 **Найдено совпадение!**\n\n"
            f"👤 **Отправитель:** {username}\n"
            f"🏗 **Чат:** {title}\n"
            f"📝 **Текст:**\n{event.text}\n\n"
            f"🔗 [Ссылка на сообщение]({link})",
            link_preview=False
        )
        except:
            logger.info(f"Ошибка отправки сообщения пользователю {user_id}")
        
    async def ask_gigachat(self, text, pos, neg, common_prompt):
        # Промпт адаптирован под GigaChat (убраны XML-теги, которые он может игнорировать)
        prompt = f"""Ты — строгий фильтр сообщений. Проанализируй текст по критериям:
1. НЕГАТИВ: Есть ли в тексте темы из списка: "{neg}"?
2. СЕМАНТИКА: Соответствует ли текст теме: "{common_prompt}"?

Текст для анализа: "{text}"

Ответь строго в формате:
NEGATIVE: (TRUE или FALSE)
SEMANTIC: (TRUE или FALSE)
FINAL: (YES или NO)

FINAL: YES ставится только если NEGATIVE: FALSE И SEMANTIC: TRUE."""

        try:
            loop = asyncio.get_event_loop()
            
            # Используем упрощенный вызов через именованные аргументы
            response = await loop.run_in_executor(
                None, 
                lambda: self.giga_client.chat(
                    Chat(
                        messages=[
                            Messages(role=MessagesRole.USER, content=prompt)
                        ],
                        model="GigaChat",
                        temperature=0.1,
                        max_tokens=100
                    )
                )
            )
            
            result = response.choices[0].message.content.upper()
            logger.info(f"✅ GigaChat LOG: {result.replace(chr(10), ' ')}")
            
            return "FINAL: YES" in result or ("NEGATIVE: FALSE" in result and "SEMANTIC: TRUE" in result)

        except Exception as e:
            if "429" in str(e):
                raise e 
            logger.error(f"GigaChat API Error: {e}")
            return False

if __name__ == "__main__":
    if not os.path.exists('data/sessions'): os.makedirs('data/sessions')
    app = ParserApp()
    asyncio.run(app.start())