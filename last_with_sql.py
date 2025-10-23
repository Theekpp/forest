import logging
import os
import sqlite3
import uuid
import signal
import sys
import threading
import queue
import asyncio
import time
import select
import platform
import json
import re
import socket
import aiosqlite
from flask import Flask, request, jsonify
try:
    import msvcrt  # Windows-only; safely imported at top
except ImportError:
    msvcrt = None
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackContext,
)
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

# Вставьте сюда ваш токен, полученный от @BotFather
# Рекомендуется использовать переменные окружения для безопасности
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не найден в переменных окружения")

# Список Telegram ID пользователей, которые могут останавливать бота
ADMIN_IDS = [
    int(admin_id) for admin_id in os.getenv("ADMIN_IDS", "730318118").split(",") if admin_id.strip()
]

# Пароль для консольной остановки (альтернативный способ)
CONSOLE_PASSWORD = os.getenv("CONSOLE_PASSWORD", "admin123")

# Максимальное количество попыток ввода пароля
MAX_PASSWORD_ATTEMPTS = int(os.getenv("MAX_PASSWORD_ATTEMPTS", "3"))

# Время блокировки в секундах после неудачных попыток
BLOCK_TIME_SECONDS = int(os.getenv("BLOCK_TIME_SECONDS", "300"))  # 5 минут

# Настройки базы данных
DB_NAME = os.getenv("DB_NAME", "bookings.db")

# Настройка логирования
# Создаем основной логгер для бота (вывод в консоль)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Создаем консольный обработчик для основных логов бота
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)
logger.addHandler(console_handler)

# Отключаем логирование httpx в консоли
httpx_logger = logging.getLogger('httpx')
httpx_logger.setLevel(logging.WARNING)  # Только ошибки и предупреждения

# Создаем файловый обработчик для httpx логов
httpx_file_handler = logging.FileHandler('httpx_logs.log', encoding='utf-8')
httpx_file_handler.setLevel(logging.WARNING)
httpx_file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
httpx_file_handler.setFormatter(httpx_file_formatter)
httpx_logger.addHandler(httpx_file_handler)

# Также создаем отдельный файл для всех логов бота
bot_file_handler = logging.FileHandler('bot_logs.log', encoding='utf-8')
bot_file_handler.setLevel(logging.INFO)
bot_file_handler.setFormatter(console_formatter)
logger.addHandler(bot_file_handler)

# Глобальная переменная для хранения приложения
application = None

# Глобальные переменные для отслеживания попыток
failed_attempts = 0
blocked_until = 0

def is_admin(user_id):
    """Проверяет, является ли пользователь администратором."""
    return user_id in ADMIN_IDS

def verify_console_password(password):
    """Проверяет пароль для консольной остановки."""
    return password == CONSOLE_PASSWORD

def is_console_blocked():
    """Проверяет, заблокирован ли доступ к консоли."""
    global blocked_until
    if blocked_until > 0:
        if time.time() < blocked_until:
            return True
        else:
            # Сброс блокировки после истечения времени
            blocked_until = 0
            failed_attempts = 0
    return False

def get_remaining_block_time():
    """Возвращает оставшееся время блокировки в секундах."""
    global blocked_until
    if blocked_until > 0:
        remaining = int(blocked_until - time.time())
        return max(0, remaining)
    return 0

def record_failed_attempt():
    """Регистрирует неудачную попытку ввода пароля."""
    global failed_attempts, blocked_until
    
    failed_attempts += 1
    logger.warning(f"Неудачная попытка ввода пароля. Попытка {failed_attempts}/{MAX_PASSWORD_ATTEMPTS}")
    
    if failed_attempts >= MAX_PASSWORD_ATTEMPTS:
        blocked_until = time.time() + BLOCK_TIME_SECONDS
        logger.error(f"Консоль заблокирована на {BLOCK_TIME_SECONDS//60} минут из-за превышения попыток.")
        return True
    return False

def reset_failed_attempts():
    """Сбрасывает счетчик неудачных попыток."""
    global failed_attempts
    failed_attempts = 0
    logger.info("Счетчик неудачных попыток сброшен.")

async def stop_bot(update: Update, context: CallbackContext) -> None:
    """Останавливает бота с отправкой сообщения (только для администраторов)."""
    if update and update.message:
        user_id = update.message.from_user.id
        if not is_admin(user_id):
            # Для неадминистраторов не отвечаем, чтобы скрыть существование команды
            logger.warning(f"Пользователь {user_id} попытался остановить бота без прав.")
            return
        
        await update.message.reply_text("🛑 Бот останавливается... Спасибо за использование!")
        logger.info(f"Бот останавливается по запросу администратора {user_id}...")
    else:
        logger.info("Бот останавливается по системному запросу...")
    
    # Запускаем остановку в отдельной задаче
    asyncio.create_task(stop_bot_async())

async def stop_bot_async():
    """Асинхронная функция для остановки бота."""
    global application
    
    if application:
        try:
            await application.stop()
            await application.shutdown()
        except Exception as e:
            logger.warning(f"Ошибка при остановке приложения: {e}")
        finally:
            application = None
    
    logger.info("Бот успешно остановлен.")
    # Используем os._exit для принудительного завершения программы
    os._exit(0)

async def stop_bot_callback(update: Update, context: CallbackContext) -> None:
    """Останавливает бота через callback кнопку (только для администраторов)."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ У вас нет прав для остановки бота.")
        logger.warning(f"Пользователь {user_id} попытался остановить бота через кнопку без прав.")
        return
    
    await query.edit_message_text("🛑 Бот останавливается... Спасибо за использование!")
    logger.info(f"Бот останавливается по запросу администратора {user_id} через кнопку...")
    
    # Запускаем остановку в отдельной задаче, чтобы не блокировать callback
    asyncio.create_task(stop_bot_async())

def safe_exit():
    """Функция для безопасного завершения программы."""
    logger.info("🛑 Начинаю безопасное завершение программы...")
    
    # 1. Останавливаем консольный поток
    try:
        if 'console_running' in globals():
            console_running.clear()
            logger.info("🛑 Консольный поток остановлен")
    except Exception as e:
        logger.error(f"Ошибка при остановке консольного потока: {e}")
    
    # 2. Безопасно останавливаем Telegram приложение
    if application:
        try:
            loop = asyncio.get_event_loop()
            if loop and not loop.is_closed():
                # Отменяем все асинхронные задачи
                for task in asyncio.all_tasks(loop):
                    if not task.done():
                        task.cancel()
                        logger.info(f"Отменена задача: {task.get_name() if hasattr(task, 'get_name') else 'Unknown'}")
                
                # Корректно останавливаем приложение
                logger.info("🛑 Останавливаю Telegram приложение...")
                loop.run_until_complete(application.stop())
                loop.run_until_complete(application.shutdown())
                
                # Останавливаем event loop
                loop.stop()
                logger.info("✅ Telegram приложение остановлено")
        except Exception as e:
            logger.error(f"Ошибка при остановке Telegram приложения: {e}")
    
    # 3. Закрываем базу данных
    try:
        # Закрываем все соединения с БД
        sqlite3.connect('file:memorydb?mode=memory&cache=shared').close()
        logger.info("✅ База данных закрыта")
    except Exception as e:
        logger.error(f"Ошибка при закрытии базы данных: {e}")
    
    logger.info("✅ Программа безопасно завершена.")
    # Используем sys.exit() вместо os._exit() для корректного завершения
    sys.exit(0)

def immediate_exit():
    """Функция для немедленного завершения программы (fallback)."""
    logger.info("🛑 Немедленное завершение программы...")
    
    # Останавливаем консольный поток
    try:
        if 'console_running' in globals():
            console_running.clear()
    except:
        pass
    
    # Принудительно останавливаем приложение
    if application:
        try:
            loop = asyncio.get_event_loop()
            if loop and not loop.is_closed():
                for task in asyncio.all_tasks(loop):
                    if not task.done():
                        task.cancel()
                loop.stop()
        except:
            pass
    
    # Немедленный выход как последний вариант
    os._exit(0)

def signal_handler(signum, frame):
    """Обработчик сигналов для безопасного завершения программы."""
    try:
        safe_exit()
    except Exception as e:
        logger.error(f"Ошибка при безопасном завершении: {e}")
        immediate_exit()

def console_monitor(async_queue, console_running, loop):
    """Мониторинг консольного ввода в отдельном потоке.
    Публикует команды в asyncio.Queue через loop.call_soon_threadsafe."""
    
    print("\n=== Консоль управления ботом ===")
    print("Доступные команды:")
    print("  stop  - остановить бота (требуется пароль)")
    print("  help  - показать доступные команды")
    print("  exit  - выйти из программы")
    print("  admins - показать список администраторов")
    print("=================================\n")
    
    while console_running.is_set():
        try:
            command = None
            # Кроссплатформенная проверка наличия ввода
            if platform.system() == 'Windows':
                if msvcrt.kbhit():  # Проверяем, есть ли ввод в буфере
                    command = input("Консоль> ").strip().lower()
            else:
                # Для Linux/Unix используем select
                if select.select([sys.stdin], [], [], 0)[0]:
                    command = sys.stdin.readline().strip().lower()
                    print(f"Консоль> {command}")  # Эхо для пользователя
            
            if command and command in ['stop', 'exit', 'quit']:
                # Проверяем, не заблокирована ли консоль
                if is_console_blocked():
                    remaining_time = get_remaining_block_time()
                    minutes = remaining_time // 60
                    seconds = remaining_time % 60
                    print(f"🚫 Доступ заблокирован. Попробуйте снова через {minutes} мин {seconds} сек.")
                    continue
                
                # Запрашиваем пароль для остановки бота
                attempts = 0
                while attempts < MAX_PASSWORD_ATTEMPTS:
                    password = input("Введите пароль для остановки бота: ").strip()
                    if verify_console_password(password):
                        print("✅ Пароль принят. Останавливаю бота...")
                        reset_failed_attempts()
                        # Публикуем команду в асинхронную очередь
                        loop.call_soon_threadsafe(async_queue.put_nowait, 'stop')
                        return
                    else:
                        attempts += 1
                        remaining_attempts = MAX_PASSWORD_ATTEMPTS - attempts
                        
                        # Регистрируем неудачную попытку
                        if record_failed_attempt():
                            print("❌ Превышено максимальное количество попыток. Доступ заблокирован на 5 минут.")
                            return
                        
                        if remaining_attempts > 0:
                            print(f"❌ Неверный пароль. Осталось попыток: {remaining_attempts}")
                        else:
                            print("❌ Превышено максимальное количество попыток. Доступ запрещен.")
                            return
                
            elif command and command == 'help':
                print("\nДоступные команды:")
                print("  stop  - остановить бота (требуется пароль)")
                print("  help  - показать доступные команды")
                print("  exit  - выйти из программы")
                print("  admins - показать список администраторов\n")
                
            elif command and command == 'admins':
                if ADMIN_IDS:
                    print("\n📋 Список администраторов (Telegram ID):")
                    for admin_id in ADMIN_IDS:
                        print(f"  - {admin_id}")
                    print()
                else:
                    print("\n⚠️  Список администраторов пуст. Добавьте ID в ADMIN_IDS.\n")
            elif command and command == '':
                continue
            elif command:
                print(f"Неизвестная команда: {command}. Введите 'help' для справки.\n")
            
            # Небольшая задержка, чтобы не нагружать CPU
            time.sleep(0.1)
                
        except EOFError:
            # Обработка Ctrl+D или закрытия stdin
            print("\nОбнаружено завершение ввода. Для остановки бота введите 'stop' и пароль.")
            continue
        except KeyboardInterrupt:
            # Обработка Ctrl+C
            print("\nДля остановки бота введите 'stop' и пароль.")
            continue
        except Exception as e:
            logger.error(f"Ошибка в мониторинге консоли: {e}")
            break

async def add_admin(update: Update, context: CallbackContext) -> None:
    """Добавляет администратора (только для существующих администраторов)."""
    if not update.message:
        return
        
    user_id = update.message.from_user.id
    if not is_admin(user_id):
        # Для неадминистраторов не отвечаем, чтобы скрыть существование команды
        return
        
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /add_admin <telegram_id>")
        return
    
    try:
        new_admin_id = int(context.args[0])
        if new_admin_id in ADMIN_IDS:
            await update.message.reply_text(f"Пользователь {new_admin_id} уже является администратором.")
        else:
            ADMIN_IDS.append(new_admin_id)
            await update.message.reply_text(f"✅ Пользователь {new_admin_id} успешно добавлен в администраторы.")
            logger.info(f"Администратор {user_id} добавил пользователя {new_admin_id} в администраторы.")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат Telegram ID. Должно быть число.")

async def remove_admin(update: Update, context: CallbackContext) -> None:
    """Удаляет администратора (только для существующих администраторов)."""
    if not update.message:
        return
        
    user_id = update.message.from_user.id
    if not is_admin(user_id):
        # Для неадминистраторов не отвечаем, чтобы скрыть существование команды
        return
    
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /remove_admin <telegram_id>")
        return
    
    try:
        remove_admin_id = int(context.args[0])
        if remove_admin_id not in ADMIN_IDS:
            await update.message.reply_text(f"Пользователь {remove_admin_id} не является администратором.")
        else:
            ADMIN_IDS.remove(remove_admin_id)
            await update.message.reply_text(f"✅ Пользователь {remove_admin_id} успешно удален из администраторов.")
            logger.info(f"Администратор {user_id} удалил пользователя {remove_admin_id} из администраторов.")
    except ValueError:
        await update.message.reply_text("❌ Неверный формат Telegram ID. Должно быть число.")

async def list_admins(update: Update, context: CallbackContext) -> None:
    """Показывает список администраторов."""
    if ADMIN_IDS:
        admin_list = "\n".join([f"• `{admin_id}`" for admin_id in ADMIN_IDS])
        await update.message.reply_text(f"📋 *Список администраторов:*\n{admin_list}", parse_mode='Markdown')
    else:
        await update.message.reply_text("⚠️ Список администраторов пуст.")

async def check_console_commands(async_queue: "asyncio.Queue[str]"):
    """Асинхронная проверка команд из asyncio.Queue без busy-loop."""
    try:
        while True:
            command = await async_queue.get()
            if command == 'stop':
                logger.info("Получена команда 'stop' из консоли...")
                asyncio.create_task(stop_bot_async())
                break
    except asyncio.CancelledError:
        # Задача была отменена при остановке бота
        logger.info("🛑 Задача проверки консольных команд отменена")
        raise  # Перебрасываем исключение для корректного завершения
    except Exception as e:
        logger.error(f"Неожиданная ошибка в задаче проверки консольных команд: {e}")
        raise

# --- Константы для текста ---

WELCOME_MESSAGE = "Добро пожаловать на шоколадную фабрику Royal Forest!"
# Мастер-классы
MC_PROGRAMS_TEXT = """
*Наши программы мастер-классов:*

Выберите программу, чтобы узнать подробности:
"""

# Отдельные тексты для каждой программы мастер-классов
MC_CHOCOLATE_TEXT = """
🍫 *Мастер-класс по приготовлению шоколада*

Погрузитесь в мир какао-бобов и создайте свою собственную уникальную плитку шоколада.

На этом мастер-классе вы:
• Познакомитесь с историей шоколада
• Научитесь отличать качественный шоколад
• Создадите свою уникальную плитку с различными добавками
• Получите готовую продукцию домой

Продолжительность: 2 часа
"""

MC_CANDY_TEXT = """
🍬 *Мастер-класс по приготовлению конфет*

Научитесь делать изысканные конфеты ручной работы с различными начинками.

На этом мастер-классе вы:
• Освоите техники приготовления конфет
• Научитесь работать с шоколадом и карамелью
• Создадите конфеты с различными начинками
• Упакуете свою продукцию в подарочную упаковку

Продолжительность: 2 часа
"""
MC_CONDITIONS_TEXT = """
*Условия и стоимость мастер-классов:*

- *Продолжительность:* 2 часа.
- *Стоимость:*
  - Группа до 5 человек включительно: 2500 руб/чел.
  - Группа от 6 человек: 2000 руб/чел.
- *Рекомендуемое время:* 19:00 - 21:00 (при желании можете выбрать другое).
- *Предоплата:* 50%. При отмене менее чем за 24 часа до мероприятия, предоплата не возвращается.
"""

# Чайная зона
TEA_PROGRAMS_TEXT = """
*Наши программы в Чайной зоне:*

Выберите программу, чтобы узнать подробности:
"""

# Отдельные тексты для каждой программы чайной зоны
TEA_RENT_TEXT = """
🍵 *Аренда чайной зоны*

Уютное пространство для вашей встречи или мероприятия.

Что включает аренда:
• Комфортное помещение для до 8 человек
• Атмосферная обстановка
• Возможность использовать свою продукцию
• Доступ к кухонной зоне

Идеально подходит для:
• Корпоративных мероприятий
• Девичников и мальчишников
• Семейных праздников
• Дружеских встреч

Стоимость: 600 руб/час (до 4 человек)
За каждого последующего гостя (с 5-го по 8-го) доплата +100 руб/час
"""

TEA_CEREMONY_TEXT = """
🌿 *Китайская чайная церемония*

Познакомьтесь с древним искусством заваривания чая.

На церемонии вы:
• Узнаете историю китайского чая
• Научитесь правильно заваривать разные сорта чая
• Пробуете редкие и эксклюзивные сорта
• Освоите чайную этику и традиции
• Почувствуете гармонию и спокойствие

Продолжительность: 1.5 часа
Стоимость: 1000 руб/чел
"""

TEA_CACAO_TEXT = """
☕️ *Какао церемония*

Ритуал, раскрывающий всю глубину вкуса и аромата настоящего какао.

На церемонии вы:
• Познакомитесь с историей какао
• Научитесь готовить напиток по традиционным рецептам
• Пробуете разные сорта какао
• Узнаете о полезных свойствах какао
• Насладитесь богатым вкусом и ароматом

Продолжительность: 1.5 часа
Стоимость: 1000 руб/чел
"""

TEA_SELF_CHOCOLATE_TEXT = """
🍫 *Самостоятельный мастер-класс по приготовлению шоколада*

Все ингредиенты и инструкции для вашего творчества.

Что включено:
• Все необходимые ингредиенты
• Пошаговые инструкции
• Инвентарь и оборудование
• Консультация мастера
• Упаковка для готовой продукции

Вы создадите:
• Уникальные шоколадные плитки
• Шоколадные фигурки
• Шоколадные конфеты

Продолжительность: 2 часа
Стоимость: 1000 руб/чел
"""

TEA_SELF_CANDY_TEXT = """
🍬 *Самостоятельный мастер-класс по приготовлению конфет*

Создайте свои конфеты в спокойной обстановке.

Что включено:
• Все необходимые ингредиенты
• Пошаговые инструкции
• Инвентарь и оборудование
• Консультация мастера
• Подарочная упаковка

Вы создадите:
• Карамельные конфеты
• Шоколадные трюфели
• Желейные конфеты
• Мармелад

Продолжительность: 2 часа
Стоимость: 1000 руб/чел
"""
TEA_CONDITIONS_TEXT = """
*Условия и стоимость в Чайной зоне:*

- *Аренда чайной зоны:* 600 руб/час (до 4 человек).
За каждого последующего гостя (с 5-го по 8-го) доплата +100 руб/час к общей сумме.
- *Китайская чайная церемония:* 1000 руб/чел.
- *Какао церемония:* 1000 руб/чел.
- *Самостоятельный МК по шоколаду:* 1000 руб/чел.
- *Самостоятельный МК по конфетам:* 1000 руб/чел.
- *Предоплата:* 50%. При отмене менее чем за 24 часа до мероприятия, предоплата не возвращается.
"""

# Контакты
CONTACTS_TEXT = """
*Контакты и время работы:*

📍 *Адрес:* г. Москва, ул. Кирпичная, д.
32к24 - https://yandex.ru/maps/-/CLEsVTMU
🕙 *Время работы магазина:* Пн-Пт, 12:00 - 20:00

📞 *Контакты магазина:* +7 (495) 972-18-01, 8 901 546 18 01, shop@royal-forest.org
📦 *Оптовый отдел:* +7 (999) 965-33-26 
👥 *Отдел франшизы:* iambolshakov@gmail.com
💼 *Отдел кадров:* iambolshakov@gmail.com
"""

# Магазин
SHOP_NEWS_TEXT = "Все наши акции и новости мы публикуем в нашем телеграм-канале: [ссылка на канал]" # Замените на реальную ссылку
SHOP_ORDER_TEXT = "Для оформления заказа, пожалуйста, посетите наш интернет-магазин: https://royal-forest.ru/" # Замените на реальную ссылку

# Константы для стоимости
MC_PRICE_UP_TO_5 = 2500
MC_PRICE_FROM_6 = 2000
TEA_RENT_BASE_PRICE = 600
TEA_RENT_ADD_GUEST_PRICE = 100
TEA_CEREMONY_PRICE = 1000
MIN_GROUP_SIZE_FOR_PROMOTIONAL_PRICE = 5
MIN_GROUP_BOOKING_PRICE = 10000

# Время работы для бронирования
BOOKING_START_HOUR = 10
BOOKING_END_HOUR = 22
LATEST_BOOKING_HOUR_TODAY = 18 # 20:00 - 2 hours for 
# duration = 18:00
LATEST_BOOKING_HOUR_FUTURE = 18 # 20:00 - 2 hours for duration = 18:00

# --- Этапы разговора для бронирования ---

# Общие этапы
CHOOSE_PROGRAM, CHOOSE_DATE, CHOOSE_TIME, GET_PEOPLE, GET_NAME, GET_PHONE = range(6)
GET_BOOKING_ID_TO_CANCEL = 7
GET_BOOKING_ID_TO_PAYMENT = 8
CHOOSE_PAYMENT_METHOD = 9

# Этапы для рассылки
BROADCAST_MENU, BROADCAST_TYPE, BROADCAST_MESSAGE, BROADCAST_CONFIRM = range(4)

# --- Клавиатуры ---

def build_main_menu(user_id=None):
    keyboard = [
        [InlineKeyboardButton("Мастер-классы", callback_data='mc_main')],
        [InlineKeyboardButton("Магазин", callback_data='shop_main')],
        [InlineKeyboardButton("Чайная зона", callback_data='tea_main')],
        [InlineKeyboardButton("Контакты, время работы", callback_data='contacts')],
        [InlineKeyboardButton("Мои бронирования", callback_data='my_bookings')]
    ]
    
    # Добавляем кнопки администратора
    if user_id and is_admin(user_id):
        keyboard.append([InlineKeyboardButton("📋 Все бронирования", callback_data='admin_bookings')])
        keyboard.append([InlineKeyboardButton("📢 Рассылка", callback_data='broadcast_menu')])
        keyboard.append([InlineKeyboardButton("📜 История рассылок", callback_data='broadcast_history')])
        keyboard.append([InlineKeyboardButton("🛑 Остановить бота", callback_data='stop_bot')])
    
    return InlineKeyboardMarkup(keyboard)

# --- Обработчики для рассылки ---

def clear_broadcast_conversation(context: CallbackContext, user_id: int) -> None:
    """Принудительно очищает состояние ConversationHandler для рассылки."""
    # Очищаем все данные рассылки
    keys_to_clear = ['broadcast_type', 'broadcast_message', 'selected_user_ids']
    for key in keys_to_clear:
        if key in context.user_data:
            del context.user_data[key]
    
    # Дополнительная очистка состояния ConversationHandler
    if hasattr(context, '_conversation') and context._conversation:
        try:
            del context._conversation
            logger.info(f"Состояние ConversationHandler очищено для пользователя {user_id}")
        except Exception as e:
            logger.warning(f"Ошибка при очистке состояния ConversationHandler: {e}")

async def broadcast_menu_start(update: Update, context: CallbackContext) -> int:
    """Начинает процесс рассылки."""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"Начало процесса рассылки от пользователя {query.from_user.id}")
    
    # Принудительная очистка предыдущего состояния
    clear_broadcast_conversation(context, query.from_user.id)
    
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ У вас нет прав для отправки рассылок.")
        logger.warning(f"Пользователь {user_id} попытался отправить рассылку без прав администратора")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("📢 Всем пользователям", callback_data='broadcast_all')],
        [InlineKeyboardButton("👥 Выбранным пользователям", callback_data='broadcast_selected')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')]
    ]
    
    await query.edit_message_text(
        "📢 <b>Рассылка сообщений</b>\n\n"
        "Выберите тип рассылки:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    return BROADCAST_TYPE

async def broadcast_type_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор типа рассылки."""
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    logger.info(f"Пользователь {query.from_user.id} выбрал тип рассылки: {choice}")
    
    if choice == 'broadcast_all':
        context.user_data['broadcast_type'] = 'all'
        await query.edit_message_text(
            "📢 <b>Рассылка всем пользователям</b>\n\n"
            "Введите текст сообщения для рассылки:\n\n"
            "<i>Поддерживается HTML-форматирование</i>",
            parse_mode='HTML'
        )
        return BROADCAST_MESSAGE
    
    elif choice == 'broadcast_selected':
        context.user_data['broadcast_type'] = 'selected'
        
        # Получаем список пользователей
        users = get_active_users()
        if not users:
            await query.edit_message_text("❌ Нет активных пользователей для рассылки.")
            return ConversationHandler.END
        
        # Формируем сообщение с выбором пользователей
        user_list = []
        for i, user in enumerate(users[:10]):  # Показываем первых 10 пользователей
            user_id = user[0]
            username = user[1] or ""
            first_name = user[2] or ""
            last_name = user[3] or ""
            
            display_name = f"@{username}" if username else f"{first_name} {last_name}".strip()
            user_list.append(f"{i+1}. {display_name} (ID: {user_id})")
        
        await query.edit_message_text(
            "👥 <b>Выборочная рассылка</b>\n\n"
            f"Всего активных пользователей: {len(users)}\n\n"
            f"Первые 10 пользователей:\n" + "\n".join(user_list) + "\n\n"
            "<i>Введите ID пользователей через запятую для рассылки:</i>",
            parse_mode='HTML'
        )
        return BROADCAST_MESSAGE
    
    elif choice == 'main_menu':
        await show_main_menu(update, context)
        return ConversationHandler.END

async def broadcast_message_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает ввод сообщения для рассылки."""
    message = update.message
    
    logger.info(f"Пользователь {message.from_user.id} ввел сообщение для рассылки")
    
    if not message.text:
        await message.reply_text("❌ Пожалуйста, введите текст сообщения.")
        return BROADCAST_MESSAGE
    
    broadcast_type = context.user_data.get('broadcast_type')
    logger.info(f"Тип рассылки: {broadcast_type}")
    
    if broadcast_type == 'selected':
        # Для выборочной рассылки сначала запрашиваем ID пользователей
        if 'selected_user_ids' not in context.user_data:
            # Сохраняем сообщение и запрашиваем ID пользователей
            context.user_data['broadcast_message'] = message.text
            await message.reply_text(
                "👥 <b>Выборочная рассылка</b>\n\n"
                "Теперь введите ID пользователей через запятую:\n\n"
                "<i>Пример: 123456789, 987654321</i>",
                parse_mode='HTML'
            )
            return BROADCAST_MESSAGE
        
        # Если ID пользователей уже введены, обрабатываем их
        user_input = message.text.strip()
        if not user_input:
            await message.reply_text("❌ Пожалуйста, введите ID пользователей через запятую.")
            return BROADCAST_MESSAGE
        
        try:
            # Разбираем ID пользователей
            user_ids = [int(uid.strip()) for uid in user_input.split(',') if uid.strip()]
            
            if not user_ids:
                await message.reply_text("❌ Не найдено корректных ID пользователей.")
                return BROADCAST_MESSAGE
            
            context.user_data['selected_user_ids'] = user_ids
            broadcast_message = context.user_data.get('broadcast_message')
            
            # Показываем подтверждение для выборочной рассылки
            keyboard = [
                [InlineKeyboardButton("✅ Отправить", callback_data='broadcast_send')],
                [InlineKeyboardButton("❌ Отмена", callback_data='broadcast_cancel')]
            ]
            
            await message.reply_text(
                "📢 <b>Подтверждение рассылки</b>\n\n"
                f"<b>Тип:</b> Выбранным пользователям\n"
                f"<b>Количество:</b> {len(user_ids)}\n"
                f"<b>ID пользователей:</b> {', '.join(map(str, user_ids))}\n\n"
                f"<b>Сообщение:</b>\n"
                f"{broadcast_message}\n\n"
                "Подтвердите отправку рассылки:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='HTML'
            )
            return BROADCAST_CONFIRM
        
        except Exception as e:
            await message.reply_text(f"❌ Ошибка при обработке ID пользователей: {e}")
            return BROADCAST_MESSAGE
    
    else:
        # Для рассылки всем сохраняем сообщение и показываем подтверждение
        context.user_data['broadcast_message'] = message.text
        
        keyboard = [
            [InlineKeyboardButton("✅ Отправить", callback_data='broadcast_send')],
            [InlineKeyboardButton("❌ Отмена", callback_data='broadcast_cancel')]
        ]
        
        await message.reply_text(
            "📢 <b>Подтверждение рассылки</b>\n\n"
            f"<b>Тип:</b> Всем пользователям\n"
            f"<b>Сообщение:</b>\n"
            f"{message.text}\n\n"
            "Подтвердите отправку рассылки:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return BROADCAST_CONFIRM

async def broadcast_confirm_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает подтверждение рассылки."""
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    logger.info(f"Пользователь {query.from_user.id} выбрал действие: {choice}")
    
    if choice == 'broadcast_cancel':
        await query.edit_message_text("❌ Рассылка отменена.")
        
        # Очищаем данные рассылки и состояние ConversationHandler
        clear_broadcast_conversation(context, query.from_user.id)
        logger.info(f"Пользователь {query.from_user.id} отменил рассылку через callback")
        
        return ConversationHandler.END
    
    elif choice == 'broadcast_send':
        broadcast_type = context.user_data.get('broadcast_type')
        message = context.user_data.get('broadcast_message')
        
        if not message:
            await query.edit_message_text("❌ Ошибка: сообщение не найдено.")
            return ConversationHandler.END
        
        # Отправляем рассылку
        await query.edit_message_text("📢 Отправляю рассылку... Пожалуйста, подождите.")
        
        logger.info(f"Начинаю отправку рассылки типа: {broadcast_type}")
        
        try:
            if broadcast_type == 'all':
                logger.info("Отправка рассылки всем пользователям")
                result = await send_broadcast_to_all(message, application)
            elif broadcast_type == 'selected':
                user_ids = context.user_data.get('selected_user_ids', [])
                logger.info(f"Отправка выборочной рассылки {len(user_ids)} пользователям")
                result = await send_broadcast_to_selected(message, user_ids, application)
            else:
                logger.error(f"Неизвестный тип рассылки: {broadcast_type}")
                await query.edit_message_text("❌ Ошибка: неизвестный тип рассылки.")
                return ConversationHandler.END
            
            # Показываем результат
            result_text = (
                f"✅ <b>Рассылка завершена!</b>\n\n"
                f"📊 <b>Статистика:</b>\n"
                f"• Всего: {result['total']}\n"
                f"• Успешно: {result['success']}\n"
                f"• Ошибок: {result['errors']}\n"
                f"• Заблокировано: {result['blocked']}"
            )
            
            await query.edit_message_text(result_text, parse_mode='HTML')
            logger.info(f"Рассылка успешно завершена: {result}")
            
            # Сохраняем рассылку в историю
            try:
                admin = query.from_user
                admin_name = f"{admin.first_name} {admin.last_name or ''}".strip()
                target_users = context.user_data.get('selected_user_ids') if broadcast_type == 'selected' else None
                
                save_broadcast_to_history(
                    admin_id=admin.id,
                    admin_username=admin.username,
                    admin_name=admin_name,
                    broadcast_type=broadcast_type,
                    message=message,
                    target_users=target_users,
                    total_sent=result['success'],
                    total_failed=result['errors'],
                    total_blocked=result['blocked']
                )
                logger.info("Рассылка сохранена в историю")
            except Exception as save_e:
                logger.error(f"Ошибка при сохранении рассылки в историю: {save_e}")
            
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка при отправке рассылки: {e}")
            logger.error(f"Ошибка при отправке рассылки: {e}")
        
        # Очищаем данные рассылки и состояние ConversationHandler
        clear_broadcast_conversation(context, query.from_user.id)
        
        return ConversationHandler.END

async def broadcast_cancel_handler(update: Update, context: CallbackContext) -> int:
    """Обрабатывает отмену рассылки."""
    await update.message.reply_text("❌ Рассылка отменена.")
    
    # Очищаем данные рассылки и состояние ConversationHandler
    clear_broadcast_conversation(context, update.message.from_user.id)
    logger.info(f"Пользователь {update.message.from_user.id} отменил рассылку")
    
    return ConversationHandler.END

async def broadcast_history_handler(update: Update, context: CallbackContext) -> None:
    """Показывает историю рассылок администратору."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ У вас нет прав для просмотра истории рассылок.")
        return
    
    # Получаем номер страницы из callback_data или используем 1
    page = 1
    if query.data and query.data.startswith('broadcast_history_page_'):
        try:
            page = int(query.data.split('_')[-1])
        except (ValueError, IndexError):
            page = 1
    
    # Получаем историю рассылок
    history_data = get_broadcast_history(page=page, per_page=5)
    
    if not history_data['broadcasts']:
        await query.edit_message_text(
            "📋 <b>История рассылок</b>\n\n"
            "Пока нет отправленных рассылок.",
            parse_mode='HTML'
        )
        return
    
    # Формируем текст с историей
    text = f"📋 <b>История рассылок</b> (страница {page}/{history_data['total_pages']})\n\n"
    
    for broadcast in history_data['broadcasts']:
        # Форматируем дату
        created_at = broadcast['created_at']
        try:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            formatted_date = dt.strftime('%d.%m.%Y %H:%M')
        except:
            formatted_date = created_at[:19] if len(created_at) > 19 else created_at
        
        # Формируем информацию о рассылке
        admin_info = f"{broadcast['admin_name']}"
        if broadcast['admin_username']:
            admin_info += f" (@{broadcast['admin_username']})"
        
        type_info = "всем пользователям" if broadcast['broadcast_type'] == 'all' else f"выбранным пользователям ({len(broadcast['target_users'] or [])})"
        
        # Обрезаем сообщение для отображения
        message_preview = broadcast['message'][:100] + "..." if len(broadcast['message']) > 100 else broadcast['message']
        
        text += (
            f"📝 <b>Рассылка #{broadcast['id']}</b>\n"
            f"👤 Администратор: {admin_info}\n"
            f"📅 Дата: {formatted_date}\n"
            f"📢 Тип: {type_info}\n"
            f"💬 Сообщение: {message_preview}\n"
            f"📊 Статистика: ✅{broadcast['total_sent']} ❌{broadcast['total_failed']} 🚫{broadcast['total_blocked']}\n"
            f"\n"
        )
    
    # Создаем клавиатуру с пагинацией
    keyboard = []
    
    # Кнопки для каждой рассылки (повторная отправка)
    for broadcast in history_data['broadcasts']:
        keyboard.append([
            InlineKeyboardButton(f"🔄 Повторить #{broadcast['id']}", callback_data=f'broadcast_resend_{broadcast["id"]}')
        ])
    
    # Кнопки навигации
    nav_buttons = []
    if history_data['page'] > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'broadcast_history_page_{history_data["page"]-1}'))
    
    nav_buttons.append(InlineKeyboardButton("⬅️ В меню", callback_data='main_menu'))
    
    if history_data['page'] < history_data['total_pages']:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f'broadcast_history_page_{history_data["page"]+1}'))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def broadcast_resend_handler(update: Update, context: CallbackContext) -> None:
    """Обрабатывает повторную отправку рассылки."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ У вас нет прав для повторной отправки рассылок.")
        return
    
    # Получаем ID рассылки из callback_data
    try:
        broadcast_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка: неверный ID рассылки.")
        return
    
    # Получаем данные рассылки
    broadcast_data = get_broadcast_by_id(broadcast_id)
    if not broadcast_data:
        await query.edit_message_text("❌ Ошибка: рассылка не найдена.")
        return
    
    # Показываем подтверждение
    message_preview = broadcast_data['message'][:200] + "..." if len(broadcast_data['message']) > 200 else broadcast_data['message']
    
    type_info = "всем пользователям" if broadcast_data['broadcast_type'] == 'all' else f"выбранным пользователям ({len(broadcast_data['target_users'] or [])})"
    
    confirmation_text = (
        f"🔄 <b>Повторная отправка рассылки</b>\n\n"
        f"📝 <b>Оригинальная рассылка #{broadcast_data['id']}</b>\n"
        f"👤 Администратор: {broadcast_data['admin_name']}\n"
        f"📅 Дата: {broadcast_data['created_at'][:19]}\n"
        f"📢 Тип: {type_info}\n"
        f"💬 Сообщение:\n"
        f"<code>{message_preview}</code>\n\n"
        f"❓ <b>Подтвердите повторную отправку</b>"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, отправить повторно", callback_data=f'broadcast_resend_confirm_{broadcast_id}')],
        [InlineKeyboardButton("❌ Отмена", callback_data='broadcast_history_page_1')]
    ]
    
    await query.edit_message_text(
        confirmation_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def broadcast_resend_confirm_handler(update: Update, context: CallbackContext) -> None:
    """Обрабатывает подтверждение повторной отправки рассылки."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ У вас нет прав для повторной отправки рассылок.")
        return
    
    # Получаем ID рассылки из callback_data
    try:
        broadcast_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Ошибка: неверный ID рассылки.")
        return
    
    # Получаем данные рассылки
    broadcast_data = get_broadcast_by_id(broadcast_id)
    if not broadcast_data:
        await query.edit_message_text("❌ Ошибка: рассылка не найдена.")
        return
    
    # Начинаем отправку
    await query.edit_message_text("📢 Отправляю повторную рассылку... Пожалуйста, подождите.")
    
    logger.info(f"Начинаю повторную отправку рассылки #{broadcast_id} типа: {broadcast_data['broadcast_type']}")
    
    try:
        if broadcast_data['broadcast_type'] == 'all':
            logger.info("Повторная отправка рассылки всем пользователям")
            result = await send_broadcast_to_all(broadcast_data['message'], application)
        elif broadcast_data['broadcast_type'] == 'selected':
            user_ids = broadcast_data['target_users'] or []
            logger.info(f"Повторная отправка выборочной рассылки {len(user_ids)} пользователям")
            result = await send_broadcast_to_selected(broadcast_data['message'], user_ids, application)
        else:
            logger.error(f"Неизвестный тип рассылки: {broadcast_data['broadcast_type']}")
            await query.edit_message_text("❌ Ошибка: неизвестный тип рассылки.")
            return
        
        # Показываем результат
        result_text = (
            f"✅ <b>Повторная рассылка завершена!</b>\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"• Всего: {result['total']}\n"
            f"• Успешно: {result['success']}\n"
            f"• Ошибок: {result['errors']}\n"
            f"• Заблокировано: {result['blocked']}"
        )
        
        await query.edit_message_text(result_text, parse_mode='HTML')
        logger.info(f"Повторная рассылка успешно завершена: {result}")
        
        # Сохраняем повторную рассылку в историю
        try:
            admin = query.from_user
            admin_name = f"{admin.first_name} {admin.last_name or ''}".strip()
            target_users = broadcast_data['target_users'] if broadcast_data['broadcast_type'] == 'selected' else None
            
            save_broadcast_to_history(
                admin_id=admin.id,
                admin_username=admin.username,
                admin_name=admin_name,
                broadcast_type=broadcast_data['broadcast_type'],
                message=broadcast_data['message'],
                target_users=target_users,
                total_sent=result['success'],
                total_failed=result['errors'],
                total_blocked=result['blocked']
            )
            logger.info("Повторная рассылка сохранена в историю")
        except Exception as save_e:
            logger.error(f"Ошибка при сохранении повторной рассылки в историю: {save_e}")
        
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка при отправке повторной рассылки: {e}")
        logger.error(f"Ошибка при отправке повторной рассылки: {e}")

# --- Клавиатуры ---

def build_mc_menu():
    keyboard = [
        [InlineKeyboardButton("Наши программы", callback_data='mc_programs')],
        [InlineKeyboardButton("Условия и стоимость", callback_data='mc_conditions')],
        [InlineKeyboardButton("Забронировать", callback_data='mc_book')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_shop_menu():
    keyboard = [
        [InlineKeyboardButton("Акции, новости", callback_data='shop_news')],
        [InlineKeyboardButton("Сделать заказ", callback_data='shop_order')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_tea_menu():
    keyboard = [
        [InlineKeyboardButton("Наши программы", callback_data='tea_programs')],
        [InlineKeyboardButton("Условия и стоимость", callback_data='tea_conditions')],
        [InlineKeyboardButton("Забронировать", callback_data='tea_book_start')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---
def init_db():
    """Инициализирует базу данных и создает таблицу бронирований, если она не существует."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            booking_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            program TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            people INTEGER NOT NULL,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            cost REAL NOT NULL,
            prepayment REAL NOT NULL,
            status TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')
    
    # Создаем таблицу для хранения пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_blocked BOOLEAN DEFAULT 0,
            last_activity TEXT,
            registered_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Создаем таблицу для хранения истории рассылок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broadcast_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            admin_username TEXT,
            admin_name TEXT,
            broadcast_type TEXT NOT NULL,
            message TEXT NOT NULL,
            target_users TEXT,  -- JSON список ID пользователей для выборочной рассылки
            total_sent INTEGER DEFAULT 0,
            total_failed INTEGER DEFAULT 0,
            total_blocked INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("База данных {} успешно инициализирована.".format(DB_NAME))

def save_user_to_db(user):
    """Сохраняет или обновляет данные пользователя в базе данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, last_name, last_activity)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        user.id,
        user.username,
        user.first_name,
        user.last_name,
        datetime.now().isoformat()
    ))
    
    conn.commit()
    conn.close()

def get_all_users():
    """Получает список всех пользователей из базы данных."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, username, first_name, last_name, is_blocked, last_activity, registered_at
        FROM users
        ORDER BY registered_at DESC
    ''')
    
    users = cursor.fetchall()
    conn.close()
    
    return users

def get_active_users():
    """Получает список активных (не заблокированных) пользователей."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, username, first_name, last_name, is_blocked, last_activity, registered_at
        FROM users
        WHERE is_blocked = 0
        ORDER BY last_activity DESC
    ''')
    
    users = cursor.fetchall()
    conn.close()
    
    return users

def block_user(user_id):
    """Блокирует пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users SET is_blocked = 1 WHERE user_id = ?
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    logger.info(f"Пользователь {user_id} заблокирован")

def unblock_user(user_id):
    """Разблокирует пользователя."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE users SET is_blocked = 0 WHERE user_id = ?
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    logger.info(f"Пользователь {user_id} разблокирован")

def save_broadcast_to_history(admin_id, admin_username, admin_name, broadcast_type, message, target_users=None, total_sent=0, total_failed=0, total_blocked=0):
    """Сохраняет рассылку в историю."""
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Преобразуем список пользователей в JSON, если он есть
    target_users_json = json.dumps(target_users) if target_users else None
    
    cursor.execute('''
        INSERT INTO broadcast_history (
            admin_id, admin_username, admin_name, broadcast_type, message, 
            target_users, total_sent, total_failed, total_blocked
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        admin_id, admin_username, admin_name, broadcast_type, message,
        target_users_json, total_sent, total_failed, total_blocked
    ))
    
    broadcast_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    logger.info(f"Рассылка сохранена в историю с ID {broadcast_id} от администратора {admin_id}")
    return broadcast_id

def get_broadcast_history(page=1, per_page=10):
    """Получает историю рассылок с пагинацией."""
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Получаем общее количество рассылок
    cursor.execute('SELECT COUNT(*) FROM broadcast_history')
    total_count = cursor.fetchone()[0]
    
    # Получаем рассылки для текущей страницы
    offset = (page - 1) * per_page
    cursor.execute('''
        SELECT id, admin_id, admin_username, admin_name, broadcast_type, message, 
               target_users, total_sent, total_failed, total_blocked, created_at
        FROM broadcast_history
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', (per_page, offset))
    
    broadcasts = cursor.fetchall()
    conn.close()
    
    # Преобразуем в удобный формат
    result = []
    for broadcast in broadcasts:
        broadcast_dict = {
            'id': broadcast[0],
            'admin_id': broadcast[1],
            'admin_username': broadcast[2],
            'admin_name': broadcast[3],
            'broadcast_type': broadcast[4],
            'message': broadcast[5],
            'target_users': json.loads(broadcast[6]) if broadcast[6] else None,
            'total_sent': broadcast[7],
            'total_failed': broadcast[8],
            'total_blocked': broadcast[9],
            'created_at': broadcast[10]
        }
        result.append(broadcast_dict)
    
    return {
        'broadcasts': result,
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'total_pages': (total_count + per_page - 1) // per_page
    }

def get_broadcast_by_id(broadcast_id):
    """Получает рассылку по ID."""
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, admin_id, admin_username, admin_name, broadcast_type, message, 
               target_users, total_sent, total_failed, total_blocked, created_at
        FROM broadcast_history
        WHERE id = ?
    ''', (broadcast_id,))
    
    broadcast = cursor.fetchone()
    conn.close()
    
    if not broadcast:
        return None
    
    return {
        'id': broadcast[0],
        'admin_id': broadcast[1],
        'admin_username': broadcast[2],
        'admin_name': broadcast[3],
        'broadcast_type': broadcast[4],
        'message': broadcast[5],
        'target_users': json.loads(broadcast[6]) if broadcast[6] else None,
        'total_sent': broadcast[7],
        'total_failed': broadcast[8],
        'total_blocked': broadcast[9],
        'created_at': broadcast[10]
    }

async def send_broadcast_to_all(message: str, application):
    """Отправляет рассылку всем активным пользователям."""
    users = get_active_users()
    success_count = 0
    error_count = 0
    blocked_count = 0
    
    logger.info(f"Начинаю рассылку сообщения {len(users)} пользователям...")
    logger.info(f"Текст сообщения: {message[:100]}...")
    
    for user in users:
        user_id = user[0]
        username = user[1]
        first_name = user[2]
        
        try:
            # Проверяем, не заблокирован ли пользователь
            if user[4]:  # is_blocked
                blocked_count += 1
                continue
            
            # Отправляем сообщение
            await application.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )
            success_count += 1
            logger.info(f"Сообщение отправлено пользователю {user_id} ({username or first_name})")
            
            # Небольшая задержка, чтобы не превысить лимиты Telegram
            await asyncio.sleep(0.05)
            
        except Exception as e:
            error_count += 1
            logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
            
            # Если пользователь заблокировал бота, отмечаем это
            if "bot was blocked by the user" in str(e) or "chat not found" in str(e):
                block_user(user_id)
    
    logger.info(f"Рассылка завершена: Успешно: {success_count}, Ошибок: {error_count}, Заблокировано: {blocked_count}")
    return {
        'total': len(users),
        'success': success_count,
        'errors': error_count,
        'blocked': blocked_count
    }

async def send_broadcast_to_selected(message: str, user_ids: list, application):
    """Отправляет рассылку выбранным пользователям."""
    success_count = 0
    error_count = 0
    blocked_count = 0
    
    logger.info(f"Начинаю рассылку сообщения {len(user_ids)} выбранным пользователям...")
    
    for user_id in user_ids:
        try:
            # Отправляем сообщение
            await application.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )
            success_count += 1
            logger.info(f"Сообщение отправлено пользователю {user_id}")
            
            # Небольшая задержка, чтобы не превысить лимиты Telegram
            await asyncio.sleep(0.05)
            
        except Exception as e:
            error_count += 1
            logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
            
            # Если пользователь заблокировал бота, отмечаем это
            if "bot was blocked by the user" in str(e) or "chat not found" in str(e):
                block_user(user_id)
                blocked_count += 1
    
    logger.info(f"Рассылка завершена: Успешно: {success_count}, Ошибок: {error_count}, Заблокировано: {blocked_count}")
    return {
        'total': len(user_ids),
        'success': success_count,
        'errors': error_count,
        'blocked': blocked_count
    }

async def save_booking_to_db(data):
    """Сохраняет данные бронирования в базу данных (async, aiosqlite)."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['booking_id'],
            data['user_id'],
            data['program'],
            data['date'],
            data['time'],
            data['people'],
            data['name'],
            data['phone'],
            data['total_cost'],
            data['prepayment'],
            data['status'],
            data['timestamp']
        ))
        await db.commit()
    logger.info("Бронирование успешно сохранено в базу данных.")

async def get_user_bookings(user_id):
    """Извлекает активные бронирования для данного пользователя (async)."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT * FROM bookings WHERE user_id = ? AND status != ? AND status != ? ORDER BY timestamp DESC', (user_id, 'отменено пользователем', 'Отменено пользователем')) as cursor:
            bookings = await cursor.fetchall()
            return bookings

async def get_all_bookings():
    """Извлекает все бронирования из базы данных для администратора (async)."""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT * FROM bookings ORDER BY timestamp DESC') as cursor:
            bookings = await cursor.fetchall()
            return bookings

async def update_booking_status(booking_id: str, new_status: str):
    """Обновляет статус бронирования (async)."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE bookings SET status = ? WHERE booking_id = ?', (new_status, booking_id))
        await db.commit()

async def update_payment_status(booking_id: str, payment_status: str):
    """Обновляет статус оплаты бронирования (async)."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE bookings SET status = ? WHERE booking_id = ?', (payment_status, booking_id))
        await db.commit()

async def confirm_and_delete_booking(update: Update, context: CallbackContext) -> int:
    """Подтверждает и удаляет выбранное бронирование."""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем полный ID бронирования из callback_data
    booking_id = query.data.replace('cancel_', '')
    
    # delete_booking_from_db(booking_id)
    await update_booking_status(booking_id, 'Отменено пользователем')
    
    message_text = f"✅ Бронирование успешно *удалено*."
    keyboard = [[InlineKeyboardButton("Мои бронирования", callback_data='my_bookings')]]
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ConversationHandler.END

'''
async def process_cancel_booking(update: Update, context: CallbackContext) -> int:
    """Обрабатывает введенный пользователем ID для отмены бронирования."""
    booking_id_prefix = update.message.text.strip()
    user_id = update.effective_user.id
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        'SELECT booking_id FROM bookings WHERE user_id = ? AND booking_id LIKE ?',
        (user_id, booking_id_prefix + '%')
    )
    booking_record = cursor.fetchone()
    conn.close()

    if booking_record:
        booking_id = booking_record[0]
        update_booking_status(booking_id, 'Отменено пользователем')
        
        # Завершаем диалог
        await update.message.reply_text(
            f"✅ Бронирование с ID `{booking_id_prefix}` успешно отменено.",
            parse_mode='Markdown',
            reply_markup=build_main_menu(update.message.from_user.id)
        )
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Бронирование с таким ID не найдено. Пожалуйста, проверьте ID и попробуйте снова.\n"
            "Или отправьте *Отмена* для выхода.",
            parse_mode='Markdown'
        )
        return GET_BOOKING_ID_TO_CANCEL 
'''

# --- Основные функции бота ---

async def start(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /start и кнопки "Главное меню"."""
    # Регистрируем/обновляем пользователя в базе данных
    if update.message and update.message.from_user:
        save_user_to_db(update.message.from_user)
    
    reply_keyboard = [[KeyboardButton("🏠 Главное меню")]]
    reply_markup = ReplyKeyboardMarkup(reply_keyboard, resize_keyboard=True, one_time_keyboard=False)

    message_text = "Добро пожаловать на шоколадную фабрику Royal Forest!\n\nИспользуйте кнопки ниже для навигации или кнопку *🏠 Главное меню*, чтобы вернуться в начало."

    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    await update.message.reply_text("Выберите категорию:", reply_markup=build_main_menu(update.message.from_user.id))

async def main_menu_from_reply_button(update: Update, context: CallbackContext) -> None:
    """Обработчик для Reply-кнопки 'Главное меню'."""
    # Регистрируем/обновляем пользователя в базе данных
    if update.message and update.message.from_user:
        save_user_to_db(update.message.from_user)
    
    await update.message.reply_text("Выберите категорию:", reply_markup=build_main_menu(update.message.from_user.id))

async def main_menu_callback(update: Update, context: CallbackContext) -> None:
    """Возвращает пользователя в главное меню после нажатия кнопки 'Назад'."""
    query = update.callback_query
    await query.answer()
    
    # Регистрируем/обновляем пользователя в базе данных
    if query.from_user:
        save_user_to_db(query.from_user)
    
    await query.edit_message_text(WELCOME_MESSAGE, reply_markup=build_main_menu(query.from_user.id))

async def show_contacts(update: Update, context: CallbackContext) -> None:
    """Показывает информацию о контактах и времени работы."""
    query = update.callback_query
    await query.answer()
    
    # Регистрируем/обновляем пользователя в базе данных
    if query.from_user:
        save_user_to_db(query.from_user)
    keyboard = [
        [InlineKeyboardButton("🌐 Наш сайт", url="https://royal-forest.ru/")],
        [InlineKeyboardButton("📍 Открыть в картах", url="https://yandex.ru/maps/-/CLEsVTMU")],
        [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')]
    ]
    await query.edit_message_text(
        CONTACTS_TEXT,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def my_bookings_handler(update: Update, context: CallbackContext) -> None:
    """Обработчик для команды /mybookings и кнопки 'Мои бронирования'."""
    query = update.callback_query if update.callback_query else None
    user = update.message.from_user if update.message else query.from_user
    user_id = user.id
    
    # Регистрируем/обновляем пользователя в базе данных
    save_user_to_db(user)
    
    bookings = await get_user_bookings(user_id)
    
    if not bookings:
        message_text = "У вас пока нет бронирований."
        keyboard = [
            [InlineKeyboardButton("➕ Добавить бронирование", callback_data='mc_book')],
            [InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')]
        ]
    else:
        message_text = "*Ваши бронирования:*\n\n"
        has_unpaid_bookings = False
        for booking in bookings:
            booking_id, user_id, program, date, time, people, name, phone, cost, prepayment, status, timestamp = booking
            message_text += (
                f"**ID:** `{booking_id[:8]}`\n"
                f"**Программа:** {program}\n"
                f"**Дата и время:** {date}, {time}\n"
                f"**Кол-во человек:** {people}\n"
                f"**Стоимость:** {int(cost)} руб. (Предоплата: {int(prepayment)} руб.)\n"
                f"**Статус:** {status}\n\n"
            )
            # Проверяем, есть ли неоплаченные бронирования
            if status.lower() not in ['оплачено', 'оплачено']:
                has_unpaid_bookings = True
        
        # Формируем кнопки в зависимости от наличия неоплаченных бронирований
        keyboard = [[InlineKeyboardButton("➕ Добавить бронирование", callback_data='mc_book')]]
        
        if has_unpaid_bookings:
            keyboard.append([InlineKeyboardButton("💳 Внести оплату", callback_data='payment_existing_booking')])
        
        keyboard.append([InlineKeyboardButton("❌ Отменить бронирование", callback_data='cancel_existing_booking')])
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')])
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def admin_bookings_handler(update: Update, context: CallbackContext) -> None:
    """Отображает все бронирования для администратора."""
    query = update.callback_query
    await query.answer()
    
    # Регистрируем/обновляем пользователя в базе данных
    if query.from_user:
        save_user_to_db(query.from_user)
    user_id = query.from_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id not in ADMIN_IDS:
        await query.edit_message_text(
            "❌ У вас нет прав для просмотра этой информации.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')]])
        )
        return
    
    # Получаем номер страницы из callback_data или устанавливаем 1
    page = 1
    if query.data and query.data.startswith('admin_bookings_page_'):
        page = int(query.data.split('_')[-1])
    
    bookings = await get_all_bookings()
    bookings_per_page = 5  # Показываем по 5 бронирований на странице
    total_bookings = len(bookings)
    total_pages = (total_bookings + bookings_per_page - 1) // bookings_per_page
    
    if not bookings:
        message_text = "📋 База данных бронирований пуста."
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data='main_menu')]]
    else:
        # Вычисляем индексы для текущей страницы
        start_idx = (page - 1) * bookings_per_page
        end_idx = start_idx + bookings_per_page
        current_bookings = bookings[start_idx:end_idx]
        
        message_text = f"📋 *Все бронирования (страница {page}/{total_pages}, всего {total_bookings}):*\n\n"
        
        for i, booking in enumerate(current_bookings, start_idx + 1):
            booking_id, user_id, program, date, time, people, name, phone, cost, prepayment, status, timestamp = booking
            # Форматируем timestamp для читаемости
            booking_date = datetime.fromisoformat(timestamp).strftime('%d.%m.%Y %H:%M')
            
            # Компактный формат вывода
            message_text += (
                f"*{i}.* `{booking_id[:8]}` | {program}\n"
                f"📅 {date} {time} | 👥 {people} чел. | 💰 {int(cost)} руб.\n"
                f"👤 {name} | 📞 {phone}\n"
                f"📊 Статус: {status} | 🕐 {booking_date}\n\n"
            )
        
        # Формируем клавиатуру с пагинацией
        keyboard = []
        
        # Кнопки навигации
        nav_buttons = []
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'admin_bookings_page_{page-1}'))
        
        nav_buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data='noop'))
        
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton("➡️ Вперед", callback_data=f'admin_bookings_page_{page+1}'))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Кнопка возврата в главное меню
        keyboard.append([InlineKeyboardButton("⬅️ В главное меню", callback_data='main_menu')])
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def notify_admins_about_new_booking(booking_data, application):
    """Отправляет уведомления всем администраторам о новом бронировании."""
    if not ADMIN_IDS:
        logger.warning("Список администраторов пуст, уведомления не отправлены")
        return
    
    booking_id, user_id, program, date, time, people, name, phone, cost, prepayment, status, timestamp = booking_data
    
    message_text = (
        f"🔔 *Новое бронирование!*\n\n"
        f"**ID бронирования:** `{booking_id[:8]}`\n"
        f"**Пользователь:** `{user_id}`\n"
        f"**Программа:** {program}\n"
        f"**Дата и время:** {date}, {time}\n"
        f"**Кол-во человек:** {people}\n"
        f"**Имя клиента:** {name}\n"
        f"**Телефон:** {phone}\n"
        f"**Общая стоимость:** {int(cost)} руб.\n"
        f"**Предоплата:** {int(prepayment)} руб.\n"
        f"**Статус:** {status}\n\n"
        f"*Для просмотра всех бронирований нажмите кнопку ниже.*"
    )
    
    keyboard = [[InlineKeyboardButton("📋 Все бронирования", callback_data='admin_bookings')]]
    
    for admin_id in ADMIN_IDS:
        try:
            await application.bot.send_message(
                chat_id=admin_id,
                text=message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            logger.info(f"Уведомление о новом бронировании отправлено администратору {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления администратору {admin_id}: {e}")


async def start_cancel_booking(update: Update, context: CallbackContext) -> int:
    """Отображает список бронирований пользователя с кнопками для отмены."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    bookings = await get_user_bookings(user_id)
    
    # Объявляем переменную 'keyboard' здесь, чтобы она была доступна всегда
    keyboard = [] 

    if not bookings:
        message_text = "❌ У вас пока нет бронирований для отмены."
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data='my_bookings')]]
        await query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ConversationHandler.END # Завершаем диалог, так как нет бронирований

    message_text = "*Ваши бронирования:*\n\n"
    for booking in bookings:
        booking_id, user_id, program, date, time, people, name, phone, cost, prepayment, status, timestamp = booking
        message_text += (
            f"**ID:** `{booking_id[:8]}`\n"
            f"**Программа:** {program}\n"
            f"**Дата и время:** {date}, {time}\n"
            f"**Кол-во человек:** {people}\n"
            f"**Стоимость:** {int(cost)} руб. (Предоплата: {int(prepayment)} руб.)\n"
            f"**Статус:** {status}\n\n"
        )
    message_text += "Выберите бронирование, которое хотите *отменить*:\n\n"
    
    for booking in bookings:
        booking_id, _, program, date, time, _, _, _, _, _, status, _ = booking
        # Используем короткий ID для отображения, но полный для callback_data
        short_id = booking_id[:8]
        button_text = f"❌ {program} от {date} на {time} (ID: {short_id})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"cancel_{booking_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='my_bookings')])

    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return GET_BOOKING_ID_TO_CANCEL


async def start_payment_booking(update: Update, context: CallbackContext) -> int:
    """Отображает список бронирований пользователя с кнопками для оплаты."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    bookings = await get_user_bookings(user_id)
    
    # Объявляем переменную 'keyboard' здесь, чтобы она была доступна всегда
    keyboard = [] 

    # Фильтруем только неоплаченные бронирования
    unpaid_bookings = []
    for booking in bookings:
        booking_id, user_id, program, date, time, people, name, phone, cost, prepayment, status, timestamp = booking
        if status.lower() not in ['оплачено', 'оплачено']:
            unpaid_bookings.append(booking)
    
    if not unpaid_bookings:
        message_text = "✅ У вас нет бронирований, ожидающих оплаты. Все бронирования оплачены!"
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data='my_bookings')]]
        await query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return ConversationHandler.END # Завершаем диалог, так как нет неоплаченных бронирований

    message_text = "*Ваши бронирования для оплаты:*\n\n"
    for booking in unpaid_bookings:
        booking_id, user_id, program, date, time, people, name, phone, cost, prepayment, status, timestamp = booking
        message_text += (
            f"**ID:** `{booking_id[:8]}`\n"
            f"**Программа:** {program}\n"
            f"**Дата и время:** {date}, {time}\n"
            f"**Кол-во человек:** {people}\n"
            f"**Стоимость:** {int(cost)} руб. (Предоплата: {int(prepayment)} руб.)\n"
            f"**Статус:** {status}\n\n"
        )
    message_text += "Выберите бронирование, для которого хотите *внести оплату*:\n\n"
    
    for booking in unpaid_bookings:
        booking_id, _, program, date, time, _, _, _, _, _, status, _ = booking
        # Используем короткий ID для отображения, но полный для callback_data
        short_id = booking_id[:8]
        button_text = f"💳 {program} от {date} на {time} (ID: {short_id})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"payment_{booking_id}")])

    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='my_bookings')])

    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return GET_BOOKING_ID_TO_PAYMENT


async def process_payment(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор бронирования для оплаты и предлагает способы оплаты."""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем полный ID бронирования из callback_data
    booking_id = query.data.replace('payment_', '')
    
    # Получаем информацию о бронировании (async)
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT * FROM bookings WHERE booking_id = ?', (booking_id,)) as cursor:
            booking = await cursor.fetchone()
    
    if not booking:
        await query.edit_message_text(
            "❌ Бронирование не найдено.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data='my_bookings')]])
        )
        return ConversationHandler.END
    
    booking_id, user_id, program, date, time, people, name, phone, cost, prepayment, status, timestamp = booking
    
    # Сохраняем booking_id в user_data для использования в следующих шагах
    context.user_data['payment_booking_id'] = booking_id
    
    # Формируем сообщение с информацией для оплаты
    payment_amount = int(cost - prepayment)
    message_text = (
        f"*Информация для оплаты:*\n\n"
        f"**ID бронирования:** `{booking_id[:8]}`\n"
        f"**Программа:** {program}\n"
        f"**Дата и время:** {date}, {time}\n"
        f"**Кол-во человек:** {people}\n"
        f"**Имя:** {name}\n"
        f"**Телефон:** {phone}\n"
        f"**Общая стоимость:** {int(cost)} руб.\n"
        f"**Предоплата:** {int(prepayment)} руб.\n"
        f"**Остаток к оплате:** {payment_amount} руб.\n\n"
        f"*Выберите способ оплаты:*"
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 Банковская карта (онлайн)", callback_data='payment_method_card')],
        [InlineKeyboardButton("📱 Перевод с ручным подтверждением", callback_data='payment_method_transfer')],
        [InlineKeyboardButton("⬅️ Назад к моим бронированиям", callback_data='my_bookings')]
    ]
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return CHOOSE_PAYMENT_METHOD


async def handle_payment_method_choice(update: Update, context: CallbackContext) -> int:
    """Обрабатывает выбор способа оплаты."""
    query = update.callback_query
    await query.answer()
    
    # Получаем сохраненный booking_id
    booking_id = context.user_data.get('payment_booking_id')
    
    if not booking_id:
        await query.edit_message_text(
            "❌ Ошибка: не найдена информация о бронировании.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data='my_bookings')]])
        )
        return ConversationHandler.END
    
    # Получаем информацию о бронировании
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT * FROM bookings WHERE booking_id = ?', (booking_id,)) as cursor:
            booking = await cursor.fetchone()
    
    if not booking:
        await query.edit_message_text(
            "❌ Бронирование не найдено.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data='my_bookings')]])
        )
        return ConversationHandler.END
    
    booking_id, user_id, program, date, time, people, name, phone, cost, prepayment, status, timestamp = booking
    payment_amount = int(cost - prepayment)
    
    # Обрабатываем выбор способа оплаты
    if query.data == 'payment_method_card':
        # Платежная система - пока недоступна
        message_text = (
            f"❌ *Платежная система временно недоступна*\n\n"
            f"**ID бронирования:** `{booking_id[:8]}`\n"
            f"**Сумма к оплате:** {payment_amount} руб.\n\n"
            f"*К сожалению, онлайн-оплата банковской картой временно недоступна. \n"
            f"Пожалуйста, выберите другой способ оплаты или свяжитесь с администратором.*"
        )
        keyboard = [
            [InlineKeyboardButton("📱 Перевод с ручным подтверждением", callback_data='payment_method_transfer')],
            [InlineKeyboardButton("⬅️ Назад к выбору способа оплаты", callback_data=f'payment_{booking_id}')],
            [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]
        ]
        
    elif query.data == 'payment_method_transfer':
        # Перевод с ручным подтверждением
        message_text = (
            f"📱 *Оплата переводом с ручным подтверждением*\n\n"
            f"**ID бронирования:** `{booking_id[:8]}`\n"
            f"**Сумма к оплате:** {payment_amount} руб.\n\n"
            f"*Реквизиты для перевода:*\n"
            f"💳 *Номер карты:* `XXXX XXXX XXXX XXXX`\n"
            f"👤 *Получатель:* ИВАНОВ ИВАН ИВАНОВИЧ\n"
            f"🏦 *Банк:* Пример Банк\n\n"
            f"*Инструкция:*\n"
            f"1. Переведите {payment_amount} руб. на указанную карту\n"
            f"2. В комментарии к переводу укажите ID бронирования: `{booking_id[:8]}`\n"
            f"3. После перевода нажмите кнопку \"Перевод отправлен\"\n"
            f"4. Администратор проверит платеж и подтвердит оплату\n\n"
            f"⚠️ *Обычно подтверждение занимает 5-30 минут в рабочее время.*"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Перевод отправлен", callback_data='transfer_sent')],
            [InlineKeyboardButton("⬅️ Назад к выбору способа оплаты", callback_data=f'payment_{booking_id}')],
            [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]
        ]
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def confirm_payment(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки 'Оплата произведена' без автоматического обновления статуса."""
    query = update.callback_query
    await query.answer()
    
    # Получаем booking_id из user_data (сохраняем его в process_payment)
    booking_id = context.user_data.get('last_payment_booking_id')
    
    if not booking_id:
        await query.edit_message_text(
            "❌ Ошибка: не найдена информация о бронировании.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data='my_bookings')]])
        )
        return
    
    # Получаем информацию о бронировании для отображения (async)
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT * FROM bookings WHERE booking_id = ?', (booking_id,)) as cursor:
            booking = await cursor.fetchone()
    
    if booking:
        booking_id, user_id, program, date, time, people, name, phone, cost, prepayment, status, timestamp = booking
        message_text = (
            f"🔄 *Оплата в обработке...*\n\n"
            f"**ID бронирования:** `{booking_id[:8]}`\n"
            f"**Программа:** {program}\n"
            f"**Дата и время:** {date}, {time}\n"
            f"**Статус:** {status}\n\n"
            f"*Ваша оплата обрабатывается платежной системой. Статус обновится после подтверждения платежа.*"
        )
    else:
        message_text = "🔄 *Оплата в обработке...*\n\n*Ваша оплата обрабатывается платежной системой.*"
    
    keyboard = [[InlineKeyboardButton("⬅️ К моим бронированиям", callback_data='my_bookings')]]
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_transfer_sent(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатие кнопки 'Перевод отправлен'."""
    query = update.callback_query
    await query.answer()
    
    # Получаем сохраненный booking_id
    booking_id = context.user_data.get('payment_booking_id')
    
    if not booking_id:
        await query.edit_message_text(
            "❌ Ошибка: не найдена информация о бронировании.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data='my_bookings')]])
        )
        return
    
    # Получаем информацию о бронировании
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT * FROM bookings WHERE booking_id = ?', (booking_id,)) as cursor:
            booking = await cursor.fetchone()
    
    if not booking:
        await query.edit_message_text(
            "❌ Бронирование не найдено.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data='my_bookings')]])
        )
        return
    
    booking_id, user_id, program, date, time, people, name, phone, cost, prepayment, status, timestamp = booking
    payment_amount = int(cost - prepayment)
    
    # Обновляем статус бронирования на "Ожидает подтверждения оплаты"
    await update_payment_status(booking_id, "Ожидает подтверждения оплаты")
    
    # Отправляем уведомление администраторам
    await notify_admins_about_payment(booking, payment_amount)
    
    message_text = (
        f"✅ *Информация о переводе получена!*\n\n"
        f"**ID бронирования:** `{booking_id[:8]}`\n"
        f"**Сумма перевода:** {payment_amount} руб.\n\n"
        f"🔄 *Статус:* Ожидает подтверждения оплаты\n\n"
        f"*Администратор получил уведомление и проверит ваш перевод. \n"
        f"Обычно подтверждение занимает 5-30 минут в рабочее время.\n\n"
        f"Вы можете отслеживать статус оплаты в разделе \"Мои бронирования\".*"
    )
    
    keyboard = [
        [InlineKeyboardButton("📋 Мои бронирования", callback_data='my_bookings')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='main_menu')]
    ]
    
    await query.edit_message_text(
        message_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def notify_admins_about_payment(booking_data, payment_amount):
    """Отправляет уведомления всем администраторам о ожидаемом платеже."""
    if not ADMIN_IDS:
        logger.warning("Список администраторов пуст, уведомления не отправлены")
        return
    
    booking_id, user_id, program, date, time, people, name, phone, cost, prepayment, status, timestamp = booking_data
    
    message_text = (
        f"💰 *Ожидается подтверждение оплаты!*\n\n"
        f"**ID бронирования:** `{booking_id[:8]}`\n"
        f"**Пользователь:** `{user_id}`\n"
        f"**Клиент:** {name}\n"
        f"**Телефон:** {phone}\n"
        f"**Программа:** {program}\n"
        f"**Дата и время:** {date}, {time}\n"
        f"**Сумма к подтверждению:** {payment_amount} руб.\n\n"
        f"⚠️ *Пользователь сообщил об отправке перевода. \n"
        f"Необходимо проверить поступление средств и подтвердить оплату.*"
    )
    
    keyboard = [[InlineKeyboardButton("📋 Все бронирования", callback_data='admin_bookings')]]
    
    for admin_id in ADMIN_IDS:
        try:
            await application.bot.send_message(
                chat_id=admin_id,
                text=message_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            logger.info(f"Уведомление об ожидаемом платеже отправлено администратору {admin_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления администратору {admin_id}: {e}")


def process_payment_webhook(payment_data):
    """Обрабатывает webhook от платежной системы и обновляет статус бронирования."""
    try:
        # Извлекаем данные из webhook (зависит от формата вашей платежной системы)
        booking_id = payment_data.get('booking_id')
        payment_status = payment_data.get('status')  # 'success', 'failed', 'pending'
        transaction_id = payment_data.get('transaction_id')
        
        if not booking_id or not payment_status:
            logger.error(f"Некорректные данные webhook: {payment_data}")
            return {'success': False, 'message': 'Некорректные данные'}
        
        # Проверяем существование бронирования (отдельный async-коннект)
        async def _fetch_booking(bid: str):
            async with aiosqlite.connect(DB_NAME) as db:
                async with db.execute('SELECT * FROM bookings WHERE booking_id = ?', (bid,)) as cursor:
                    return await cursor.fetchone()
        booking = asyncio.run(_fetch_booking(booking_id))
        
        if not booking:
            logger.error(f"Бронирование не найдено: {booking_id}")
            return {'success': False, 'message': 'Бронирование не найдено'}
        
        # Обновляем статус в зависимости от результата платежа
        if payment_status == 'success':
            new_status = 'Оплачено'
        elif payment_status == 'failed':
            new_status = 'Оплата отклонена'
        else:
            new_status = 'Оплата в обработке'
        
        # Обновляем статус в базе данных (async в отдельном loop)
        async def _update():
            await update_payment_status(booking_id, new_status)
        asyncio.run(_update())
        
        # Логируем транзакцию
        logger.info(f"Платеж для бронирования {booking_id}: статус {payment_status}, транзакция {transaction_id}")
        
        # Здесь можно добавить отправку уведомления пользователю в Telegram
        # if payment_status == 'success':
        #     send_payment_success_notification(booking_id)
        
        return {'success': True, 'message': f'Статус обновлен: {new_status}'}
        
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return {'success': False, 'message': f'Ошибка: {str(e)}'}


# --- Логика Мастер-классов ---

async def mc_main_menu(update: Update, context: CallbackContext) -> None:
    """Отображает главное меню раздела 'Мастер-классы'."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Раздел: Мастер-классы", reply_markup=build_mc_menu())

async def mc_programs(update: Update, context: CallbackContext) -> None:
    """Показывает программы мастер-классов."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🍫 МК по шоколаду", callback_data="mc_chocolate_details")],
        [InlineKeyboardButton("🍬 МК по конфетам", callback_data="mc_candy_details")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="mc_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=MC_PROGRAMS_TEXT,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def mc_conditions(update: Update, context: CallbackContext) -> None:
    """Показывает условия и стоимость мастер-классов."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Забронировать", callback_data="mc_book")],
        [InlineKeyboardButton("Назад", callback_data="mc_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=MC_CONDITIONS_TEXT,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def mc_chocolate_details(update: Update, context: CallbackContext) -> None:
    """Показывает подробности о мастер-классе по приготовлению шоколада."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Забронировать", callback_data="mc_book_chocolate")],
        [InlineKeyboardButton("⬅️ Назад к программам", callback_data="mc_programs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=MC_CHOCOLATE_TEXT,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def mc_candy_details(update: Update, context: CallbackContext) -> None:
    """Показывает подробности о мастер-классе по приготовлению конфет."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Забронировать", callback_data="mc_book_candy")],
        [InlineKeyboardButton("⬅️ Назад к программам", callback_data="mc_programs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=MC_CANDY_TEXT,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# --- Логика Магазина ---

async def shop_main_menu(update: Update, context: CallbackContext) -> None:
    """Отображает главное меню раздела 'Магазин'."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Раздел: Магазин", reply_markup=build_shop_menu())

async def shop_news(update: Update, context: CallbackContext) -> None:
    """Показывает акции и новости магазина."""
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data='shop_main')]]
    await query.edit_message_text(
        SHOP_NEWS_TEXT,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown',
        disable_web_page_preview=True
    )
    
async def shop_order(update: Update, context: CallbackContext) -> None:
    """Предлагает сделать заказ через интернет-магазин."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🛒 Перейти в магазин", url='https://royal-forest.ru/shop')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='shop_main')]
    ]
    await query.edit_message_text(
        SHOP_ORDER_TEXT,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown',
        disable_web_page_preview=True
    )

# --- Логика Чайной зоны ---

async def tea_main_menu(update: Update, context: CallbackContext) -> None:
    """Отображает главное меню раздела 'Чайная зона'."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(text="Раздел: Чайная зона", reply_markup=build_tea_menu())

async def tea_programs(update: Update, context: CallbackContext) -> None:
    """Показывает программы в чайной зоне."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🍵 Аренда чайной зоны", callback_data="tea_rent_details")],
        [InlineKeyboardButton("🌿 Чайная церемония", callback_data="tea_ceremony_details")],
        [InlineKeyboardButton("☕️ Какао церемония", callback_data="tea_cacao_details")],
        [InlineKeyboardButton("🍫 МК по шоколаду", callback_data="tea_self_chocolate_details")],
        [InlineKeyboardButton("🍬 МК по конфетам", callback_data="tea_self_candy_details")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="tea_main")]
    ]
    await query.edit_message_text(
        TEA_PROGRAMS_TEXT,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def tea_conditions(update: Update, context: CallbackContext) -> None:
    """Показывает условия и стоимость в чайной зоне."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Забронировать", callback_data='tea_book_start')],
        [InlineKeyboardButton("⬅️ Назад", callback_data='tea_main')]
    ]
    await query.edit_message_text(
        TEA_CONDITIONS_TEXT,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def tea_rent_details(update: Update, context: CallbackContext) -> None:
    """Показывает подробности об аренде чайной зоны."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Забронировать", callback_data="tea_book_rent")],
        [InlineKeyboardButton("⬅️ Назад к программам", callback_data="tea_programs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=TEA_RENT_TEXT,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def tea_ceremony_details(update: Update, context: CallbackContext) -> None:
    """Показывает подробности о китайской чайной церемонии."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Забронировать", callback_data="tea_book_ceremony")],
        [InlineKeyboardButton("⬅️ Назад к программам", callback_data="tea_programs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=TEA_CEREMONY_TEXT,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def tea_cacao_details(update: Update, context: CallbackContext) -> None:
    """Показывает подробности о какао церемонии."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Забронировать", callback_data="tea_book_cacao")],
        [InlineKeyboardButton("⬅️ Назад к программам", callback_data="tea_programs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=TEA_CACAO_TEXT,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def tea_self_chocolate_details(update: Update, context: CallbackContext) -> None:
    """Показывает подробности о самостоятельном мастер-классе по шоколаду."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Забронировать", callback_data="tea_book_self_chocolate")],
        [InlineKeyboardButton("⬅️ Назад к программам", callback_data="tea_programs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=TEA_SELF_CHOCOLATE_TEXT,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def tea_self_candy_details(update: Update, context: CallbackContext) -> None:
    """Показывает подробности о самостоятельном мастер-классе по конфетам."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Забронировать", callback_data="tea_book_self_candy")],
        [InlineKeyboardButton("⬅️ Назад к программам", callback_data="tea_programs")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text=TEA_SELF_CANDY_TEXT,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# --- Логика Бронирования (ConversationHandler) ---

# Шаг 1: Выбор программы
async def mc_book_start(update: Update, context: CallbackContext) -> int:
    """Начинает процесс бронирования мастер-класса."""
    query = update.callback_query
    await query.answer()
    
    # Регистрируем/обновляем пользователя в базе данных
    if query.from_user:
        save_user_to_db(query.from_user)
    context.user_data['booking_type'] = 'mc'
    keyboard = [
        [InlineKeyboardButton("МК по шоколаду", callback_data='МК по шоколаду')],
        [InlineKeyboardButton("МК по конфетам", callback_data='МК по конфетам')],
        [InlineKeyboardButton("Отмена", callback_data='cancel_booking')],
    ]
    await query.edit_message_text(
        "Выберите программу мастер-класса:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_PROGRAM

async def tea_book_start(update: Update, context: CallbackContext) -> int:
    """Начинает процесс бронирования в чайной зоне."""
    query = update.callback_query
    await query.answer()
    
    # Регистрируем/обновляем пользователя в базе данных
    if query.from_user:
        save_user_to_db(query.from_user)
    context.user_data['booking_type'] = 'tea'
    keyboard = [
        [InlineKeyboardButton("Аренда чайной зоны", callback_data='Аренда чайной зоны')],
        [InlineKeyboardButton("Китайская чайная церемония", callback_data='Китайская чайная церемония')],
        [InlineKeyboardButton("Какао церемония", callback_data='Какао церемония')],
        [InlineKeyboardButton("Самостоятельный МК (шоколад)", callback_data='Самостоятельный МК (шоколад)')],
        [InlineKeyboardButton("Самостоятельный МК (конфеты)", callback_data='Самостоятельный МК (конфеты)')],
        [InlineKeyboardButton("Отмена", callback_data='cancel_booking')],
    ]
    await query.edit_message_text(
        "Выберите программу в чайной зоне:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_PROGRAM

# Шаг 2: Получение программы и запрос даты
async def choose_program(update: Update, context: CallbackContext) -> int:
    """Сохраняет выбранную программу и запрашивает дату."""
    query = update.callback_query
    await query.answer()
    context.user_data['program'] = query.data
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_program')],
        [InlineKeyboardButton("Отмена", callback_data='cancel_booking')],
    ]
    await query.edit_message_text(
        text=f"Выбрана программа: *{query.data}*\n\nТеперь введите желаемую дату (например, 25.08.2025):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return CHOOSE_DATE

# Шаг 3: Получение даты и запрос времени
async def choose_date(update: Update, context: CallbackContext) -> int:
    """Сохраняет дату и запрашивает время."""
    user_date = update.message.text.strip()
    
    # Валидация даты
    try:
        date_obj = datetime.strptime(user_date, '%d.%m.%Y').date()
        today = datetime.today().date()
        
        # Проверяем, что дата не в прошлом
        if date_obj < today:
            await update.message.reply_text("❌ Нельзя выбрать прошедшую дату. Пожалуйста, введите корректную дату (например, 25.08.2025):")
            return CHOOSE_DATE
            
        # Проверяем, что дата не слишком далеко в будущем (например, не более 1 года вперед)
        max_date = today.replace(year=today.year + 1)
        if date_obj > max_date:
            await update.message.reply_text(f"❌ Бронирование доступно не более чем на год вперед. Пожалуйста, выберите дату до {max_date.strftime('%d.%m.%Y')}:")
            return CHOOSE_DATE
            
        context.user_data['date'] = user_date
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_program')],
   
            [InlineKeyboardButton("Отмена", callback_data='cancel_booking')],
        ]
        await update.message.reply_text(
            f"📅 Дата: *{user_date}*\n\nВведите желаемое время (например, 19:00):",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return CHOOSE_TIME
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ (например, 25.08.2025):")
        return CHOOSE_DATE
    
# Шаг 4: Получение времени и запрос кол-ва людей
async def choose_time(update: Update, context: CallbackContext) -> int:
    """Обработка выбора времени."""
    user_time = update.message.text.strip()
    
    try:
        time_obj = datetime.strptime(user_time, '%H:%M').time()
        now = datetime.now()
        current_date = now.date()
        current_time = now.time()
        
        # Проверяем, что время в рабочем диапазоне
        if time_obj < datetime.strptime(f'{BOOKING_START_HOUR}:00', '%H:%M').time() or \
           time_obj > datetime.strptime(f'{BOOKING_END_HOUR}:00', '%H:%M').time():
            keyboard = [
                [
                    InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_time'),
                    InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')
                ]
            ]
            await update.message.reply_text(
                f"❌ Время работы с {BOOKING_START_HOUR}:00 до {BOOKING_END_HOUR}:00."
                "Пожалуйста, выберите время в этом интервале (например, 19:00):",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return CHOOSE_TIME
        
        # Если выбрана сегодняшняя дата
        if current_date == datetime.strptime(context.user_data['date'], '%d.%m.%Y').date():
            # Проверяем, что выбранное время не в прошлом
            if time_obj < current_time:
                keyboard = [
                    [
                        InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_time'),
                        InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')
                    ]
                ]
                await update.message.reply_text(
                    "❌ Нельзя выбрать прошедшее время. "
                    "Пожалуйста, выберите более позднее время:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return CHOOSE_TIME
            
            # Проверяем, что до конца бронирования (через 2 часа) не позднее чем LATEST_BOOKING_HOUR_TODAY
            if datetime.combine(datetime.strptime(context.user_data['date'], '%d.%m.%Y').date(), time_obj) + timedelta(hours=2) > datetime.combine(datetime.strptime(context.user_data['date'], '%d.%m.%Y').date(), datetime.strptime(f'{BOOKING_END_HOUR}:00', '%H:%M').time()):
                latest_possible_time_obj = (datetime.combine(datetime.strptime(context.user_data['date'], '%d.%m.%Y').date(), datetime.strptime(f'{BOOKING_END_HOUR}:00', '%H:%M').time()) - timedelta(hours=2)).time()
                keyboard = [
                    [
                        InlineKeyboardButton("📅 Выбрать другую дату", 
                            callback_data='back_to_date'),
                        InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')
                    ]
                ]
                await update.message.reply_text(
                    f"❌ На сегодня запись уже закрыта. Бронирование возможно не позднее чем за 2 часа до закрытия ({BOOKING_END_HOUR}:00)."
                    f"Пожалуйста, выберите другой день или время до {latest_possible_time_obj.strftime('%H:%M')}:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return CHOOSE_TIME
        else: # Для будущих дат
            # Проверяем, что бронирование возможно не позднее чем за 2 часа до закрытия (20:00)
            if datetime.strptime(context.user_data['date'], '%d.%m.%Y').date() == datetime.today().date() and datetime.strptime(user_time, '%H:%M').time() > datetime.strptime(f'{LATEST_BOOKING_HOUR_TODAY}:00', '%H:%M').time():
                latest_booking_str = datetime.strptime(f'{LATEST_BOOKING_HOUR_TODAY}:00', '%H:%M').strftime('%H:%M')
                keyboard = [
                    [
                        InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_time'),
                        InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')
                    ]
                ]
                await update.message.reply_text(
                    f"❌ Бронирование возможно не позднее чем за 2 часа до закрытия ({BOOKING_END_HOUR}:00)."
                    f"Пожалуйста, выберите время до {latest_booking_str}:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return CHOOSE_TIME
            
    except ValueError:
        keyboard = [
            [
                InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_time'),
                InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')
            ]
        ]
        await update.message.reply_text(
            "❌ Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ (например, 19:00):",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return CHOOSE_TIME

    context.user_data['time'] = user_time
    max_people = 8  # Максимальное количество человек
    keyboard = [
        [
            InlineKeyboardButton("⬅️ Назад", callback_data='back_to_time'),
            InlineKeyboardButton("🔄 Заново", callback_data='reenter_time')
        ],
        [
            InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')
        ]
    ]
    await update.message.reply_text(
        f"🕒 Время: *{user_time}*\n\n"
        f"Введите количество человек (от 1 до {max_people}):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return GET_PEOPLE

# Шаг 5: Получение кол-ва людей и запрос имени
async def get_people(update: Update, context: CallbackContext) -> int:
    """Сохраняет количество человек и запрашивает имя."""
    try:
        num_people = int(update.message.text.strip())
        max_people = 8  # Максимальное количество человек
        
        if num_people <= 0:
            await update.message.reply_text("❌ Количество человек должно быть больше нуля. Пожалуйста, введите корректное число:")
            return GET_PEOPLE
            
        if num_people > max_people:
            await update.message.reply_text(
                f"❌ Максимальное количество человек для бронирования - {max_people}. "
                f"Для групп большего размера, пожалуйста, свяжитесь с нами по телефону."
            )
            return GET_PEOPLE
            
        context.user_data['people'] = num_people
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_time')],
            [InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_people')],
            [InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')]
        ]
        await update.message.reply_text(
            "👤 Отлично! Теперь введите Ваше имя:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return GET_NAME
        
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите количество человек цифрами (например, 2 или 4):")
        return GET_PEOPLE

# Шаг 6: Получение имени и запрос телефона
async def get_name(update: Update, context: CallbackContext) -> int:
    """Сохраняет имя и запрашивает контактный телефон."""
    user_name = update.message.text.strip()
    
    # Проверка на минимальную длину имени
    if len(user_name) < 2:
        await update.message.reply_text("❌ Имя слишком короткое. Пожалуйста, введите Ваше полное имя:")
        return GET_NAME
        
    # Проверка на наличие только букв и пробелов (можно добавить дефисы и апострофы)
    if not all(c.isalpha() or c.isspace() or c in "-'" for c in user_name):
        await update.message.reply_text("❌ Имя содержит недопустимые символы. Пожалуйста, используйте только буквы, пробелы и дефисы:")
        return GET_NAME
    
    context.user_data['name'] = user_name
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_people')],
        [InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_name')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')]
    ]
    await update.message.reply_text(
        "📱 Спасибо! И последний шаг: введите Ваш контактный телефон "
        "в формате +7XXXXXXXXXX или 8XXXXXXXXXX:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GET_PHONE

# Шаг 7: Финал - получение телефона, расчет и вывод информации
async def get_phone(update: Update, context: CallbackContext) -> int:
    """Сохраняет телефон, рассчитывает стоимость и выводит итоговую информацию о бронировании."""
    user_phone = update.message.text.strip()
    
    # Валидация номера телефона
    # Проверяем формат: +7XXXXXXXXXX, 8XXXXXXXXXX, 7XXXXXXXXXX
    phone_pattern = re.compile(r'^(\+7|8|7)?\d{10}$')
    
    if not phone_pattern.match(user_phone):
        await update.message.reply_text(
            "❌ Неверный формат номера телефона. "
            "Пожалуйста, введите номер в формате +7XXXXXXXXXX или 8XXXXXXXXXX:"
        )
        return GET_PHONE
    
    # Приводим номер к единому формату +7XXXXXXXXXX
    if user_phone.startswith('8'):
        user_phone = '+7' + user_phone[1:]
    elif user_phone.startswith('7'):
        user_phone = '+' + user_phone
    elif not user_phone.startswith('+7') and not user_phone.startswith('8'): # Если просто 10 цифр
        user_phone = '+7' + user_phone
    
    context.user_data['phone'] = user_phone

    # --- Расчет стоимости ---
    booking_type = context.user_data['booking_type']
    program = context.user_data['program']
    people = context.user_data['people']
    total_cost = 0

    if booking_type == 'mc':
        if people < MIN_GROUP_SIZE_FOR_PROMOTIONAL_PRICE:
            total_cost = MIN_GROUP_BOOKING_PRICE
        else:
            if people >= 6:
                total_cost = MC_PRICE_FROM_6 * people
            else:
                total_cost = MC_PRICE_UP_TO_5 * people
    elif booking_type == 'tea':
        if program == 'Аренда чайной зоны':
            if people > 4:
                total_cost = TEA_RENT_BASE_PRICE + (people - 4) * TEA_RENT_ADD_GUEST_PRICE
            else:
                total_cost = TEA_RENT_BASE_PRICE
        else:  # Все остальные программы в чайной зоне
            if people < MIN_GROUP_SIZE_FOR_PROMOTIONAL_PRICE:
                total_cost = MIN_GROUP_BOOKING_PRICE
            else:
                total_cost = TEA_CEREMONY_PRICE * people
    
    prepayment = total_cost / 2

    # --- Сохранение бронирования в базу данных ---
    booking_data = {
        'booking_id': str(uuid.uuid4()),
        'user_id': update.effective_user.id,
        'program': context.user_data['program'],
        'date': context.user_data['date'],
        'time': context.user_data['time'],
        'people': context.user_data['people'],
        'name': context.user_data['name'],
        'phone': user_phone,
        'total_cost': total_cost,
        'prepayment': prepayment,
        'status': 'Ожидает оплаты', # Начальный статус бронирования
        'timestamp': datetime.now().isoformat()
    }
    await save_booking_to_db(booking_data)
    
    # Отправляем уведомления администраторам
    # Получаем данные бронирования в кортеже для функции уведомления
    booking_tuple = (
        booking_data['booking_id'],
        booking_data['user_id'],
        booking_data['program'],
        booking_data['date'],
        booking_data['time'],
        booking_data['people'],
        booking_data['name'],
        booking_data['phone'],
        booking_data['total_cost'],
        booking_data['prepayment'],
        booking_data['status'],
        booking_data['timestamp']
    )
    
    # Отправляем уведомление администраторам
    await notify_admins_about_new_booking(booking_tuple, context.application)

    # --- Формирование итогового сообщения ---
    # Формируем сообщение о стоимости с учетом минимальной группы
    cost_info = f"*Итоговая стоимость:* {total_cost} руб."
    if people < MIN_GROUP_SIZE_FOR_PROMOTIONAL_PRICE:
        cost_info = (
            f"*Внимание!* Минимальная группа для МК - {MIN_GROUP_SIZE_FOR_PROMOTIONAL_PRICE - 1} человека.\n"
            f"При бронировании для {people} человек действует минимальная стоимость {MIN_GROUP_BOOKING_PRICE} руб.\n\n"
            f"*Итоговая стоимость:* {total_cost} руб.\n"
            f"(Присоединитесь к группе от {MIN_GROUP_SIZE_FOR_PROMOTIONAL_PRICE} человек, чтобы сэкономить!)"
        )
    # Специальное сообщение для аренды чайной зоны, если количество людей меньше 4
    elif booking_type == 'tea' and program == 'Аренда чайной зоны' and people <= 4:
        cost_info = (
            f"*Итоговая стоимость:* {total_cost} руб.\n"
            f"(Аренда чайной зоны до 4 человек.)\n"
        )


    summary = f"""
*Ваша заявка на бронирование:*

*Программа:* {context.user_data['program']}
*Дата:* {context.user_data['date']}
*Время:* {context.user_data['time']}
*Количество человек:* {context.user_data['people']}
*Имя:* {context.user_data['name']}
*Телефон:* {context.user_data['phone']}

{cost_info}
*К предоплате (50%):* {prepayment} руб.
Наш менеджер свяжется с вами в ближайшее время для подтверждения.
Для завершения бронирования, пожалуйста, внесите предоплату.
"""
    # URL для оплаты (замените на реальную ссылку)
    payment_url = 'https://www.example.com/pay'
    keyboard = [
        [InlineKeyboardButton("💳 Внести предоплату", url=payment_url)],
        [InlineKeyboardButton("Главное меню", callback_data='exit_conversation_to_main_menu')]
    ]
    
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    # Здесь можно добавить логику сохранения данных бронирования
    logger.info("Заявка на бронирование: %s", context.user_data)
    context.user_data.clear() # Очищаем данные после завершения
    return ConversationHandler.END

# Отмена
async def cancel_booking(update: Update, context: CallbackContext) -> int:
    """Отменяет процесс бронирования."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Бронирование отменено.",
        reply_markup=build_main_menu(query.from_user.id)
    )
    context.user_data.clear()
    return ConversationHandler.END

async def exit_conversation_to_main_menu(update: Update, context: CallbackContext) -> int:
    """Возвращает пользователя в главное меню и завершает ConversationHandler."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(WELCOME_MESSAGE, reply_markup=build_main_menu(query.from_user.id))
    context.user_data.clear() # Очищаем данные на всякий случай
   
    return ConversationHandler.END

# --- Вспомогательные функции для навигации ConversationHandler ---

async def back_to_program_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    # Восстанавливаем меню выбора программы в зависимости от типа бронирования
    if context.user_data.get('booking_type') == 'mc':
        keyboard = [
            [InlineKeyboardButton("МК по шоколаду", callback_data='МК по шоколаду')],
            [InlineKeyboardButton("МК по конфетам", callback_data='МК по конфетам')],
            [InlineKeyboardButton("Отмена", callback_data='cancel_booking')],
        ]
        await query.edit_message_text("Выберите программу мастер-класса:", reply_markup=InlineKeyboardMarkup(keyboard))
    else: # tea_booking
        keyboard = [
            [InlineKeyboardButton("Аренда чайной зоны", callback_data='Аренда чайной зоны')],
            [InlineKeyboardButton("Китайская чайная церемония", callback_data='Китайская чайная церемония')],
            [InlineKeyboardButton("Какао церемония", callback_data='Какао церемония')],
            [InlineKeyboardButton("Самостоятельный МК (шоколад)", callback_data='Самостоятельный МК (шоколад)')],
            [InlineKeyboardButton("Самостоятельный МК (конфеты)", callback_data='Самостоятельный МК (конфеты)')],
            [InlineKeyboardButton("Отмена", callback_data='cancel_booking')],
        ]
        await query.edit_message_text("Выберите программу в чайной зоне:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_PROGRAM

async def reenter_date_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_program')],
   
        [InlineKeyboardButton("Отмена", callback_data='cancel_booking')],
    ]
    await query.edit_message_text(
        "Пожалуйста, введите желаемую дату (например, 25.08.2025):",
        reply_markup=InlineKeyboardMarkup(keyboard) # Возвращаем кнопки "Назад" и "Отмена"
    )
    return CHOOSE_DATE

async def back_to_date_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_program')], # Назад к выбору программы
        [InlineKeyboardButton("Отмена", callback_data='cancel_booking')],
 
    ]
    await query.edit_message_text(
        "📅 Введите желаемую дату (ДД.ММ.ГГГГ):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_DATE

async def reenter_time_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_date')],
        [InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_time')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')]
    ]
  
    await query.edit_message_text(
        "🕒 Введите желаемое время (ЧЧ:ММ):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSE_TIME

async def back_to_time_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_date')],
        [InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_time')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')]
    ]
    await query.edit_message_text(
  
       f"🕒 Время: *{context.user_data.get('time', 'не выбрано')}*\n\n" # Показываем предыдущее время
        f"Введите желаемое время (ЧЧ:ММ):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return CHOOSE_TIME


async def reenter_people_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    max_people = 8
    keyboard = [
        [
            InlineKeyboardButton("⬅️ Назад", callback_data='back_to_time'),
            InlineKeyboardButton("🔄 Заново", callback_data='reenter_people')
        ],
        [
            InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')
        ]
    ]
    await query.edit_message_text(
        f"Введите количество человек (от 1 до {max_people}):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GET_PEOPLE

async def back_to_people_handler(update: Update, 
context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    max_people = 8
    keyboard = [
        [
            InlineKeyboardButton("⬅️ Назад", callback_data='back_to_time'),
            InlineKeyboardButton("🔄 Заново", callback_data='reenter_people')
        ],
        [
            InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')
        ]
    ]
    await query.edit_message_text(
        f"Введите количество человек (от 1 до {max_people}):",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GET_PEOPLE

async def reenter_name_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_people')],
        [InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_name')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')]
 
]
    await query.edit_message_text(
        "👤 Пожалуйста, введите Ваше имя:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GET_NAME

async def back_to_name_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_people')],
        [InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_name')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')]
    ]
  
    await query.edit_message_text(
        "👤 Пожалуйста, введите Ваше имя:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GET_NAME


async def reenter_phone_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_name')],
        [InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_phone')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')]
    ]
    await query.edit_message_text(
  
       "📱 Введите Ваш контактный телефон в формате +7XXXXXXXXXX или 8XXXXXXXXXX:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GET_PHONE

async def back_to_phone_handler(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⬅️ Назад", callback_data='back_to_name')],
        [InlineKeyboardButton("🔄 Ввести заново", callback_data='reenter_phone')],
        [InlineKeyboardButton("🏠 В главное меню", callback_data='exit_conversation_to_main_menu')]
    ]
    await query.edit_message_text(
  
       "📱 Введите Ваш контактный телефон в формате +7XXXXXXXXXX или 8XXXXXXXXXX:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return GET_PHONE


def main() -> None:
    # Регистрируем обработчики сигналов для graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Инициализируем базу данных при старте
    init_db()

    # Создаем приложение и сохраняем в глобальную переменную
    global application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Создаем asyncio.Queue для консольных команд и запускаем мониторинг
    global console_running
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    async_queue: asyncio.Queue[str] = asyncio.Queue()
    # Добавляем флаг завершения для консольного потока
    console_running = threading.Event()
    console_running.set()
    console_thread = threading.Thread(target=console_monitor, args=(async_queue, console_running, loop), daemon=True)
    console_thread.start()
    
    # Запускаем задачу для проверки консольных команд
    loop.create_task(check_console_commands(async_queue))

    # --- Регистрация всех обработчиков ---
    
    # Обработчик бронирования с навигацией
    booking_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(mc_book_start, pattern='^mc_book$'),
            CallbackQueryHandler(tea_book_start, pattern='^tea_book_start$'),
            CallbackQueryHandler(start_cancel_booking, pattern='^cancel_existing_booking$'),
            CallbackQueryHandler(mc_book_start, pattern='^mc_book_chocolate$'),
            CallbackQueryHandler(mc_book_start, pattern='^mc_book_candy$'),
            CallbackQueryHandler(tea_book_start, pattern='^tea_book_rent$'),
            CallbackQueryHandler(tea_book_start, pattern='^tea_book_ceremony$'),
            CallbackQueryHandler(tea_book_start, pattern='^tea_book_cacao$'),
            CallbackQueryHandler(tea_book_start, pattern='^tea_book_self_chocolate$'),
            CallbackQueryHandler(tea_book_start, pattern='^tea_book_self_candy$'),
            CallbackQueryHandler(start_payment_booking, pattern='^payment_existing_booking$')
        ],
        states={
            CHOOSE_PROGRAM: [
                CallbackQueryHandler(choose_program, pattern='^(?!cancel_booking|back_to_|reenter_).*$'),
                # Кнопки "Назад" здесь нет, только "Отмена"
            ],
            
            CHOOSE_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_date),
                CallbackQueryHandler(back_to_program_handler, pattern='^back_to_program$'),
                CallbackQueryHandler(reenter_date_handler, pattern='^reenter_date$'),
                CallbackQueryHandler(exit_conversation_to_main_menu, pattern='^exit_conversation_to_main_menu$'),
            ],
            CHOOSE_TIME: [
    
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_time),
                CallbackQueryHandler(back_to_date_handler, pattern='^back_to_date$'),
                CallbackQueryHandler(reenter_time_handler, pattern='^reenter_time$'),
                CallbackQueryHandler(exit_conversation_to_main_menu, pattern='^exit_conversation_to_main_menu$'),
            ],
            GET_PEOPLE: [
         
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_people),
                CallbackQueryHandler(back_to_time_handler, pattern='^back_to_time$'),
                CallbackQueryHandler(reenter_people_handler, pattern='^reenter_people$'),
                CallbackQueryHandler(exit_conversation_to_main_menu, pattern='^exit_conversation_to_main_menu$'),
            ],
            GET_NAME: [
              
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_name),
                CallbackQueryHandler(back_to_people_handler, pattern='^back_to_people$'),
                CallbackQueryHandler(reenter_name_handler, pattern='^reenter_name$'),
                CallbackQueryHandler(exit_conversation_to_main_menu, pattern='^exit_conversation_to_main_menu$'),
            ],
            GET_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone),
                CallbackQueryHandler(back_to_name_handler, pattern='^back_to_name$'),
                CallbackQueryHandler(reenter_phone_handler, pattern='^reenter_phone$'),
                CallbackQueryHandler(exit_conversation_to_main_menu, pattern='^exit_conversation_to_main_menu$'),
            ],
            GET_BOOKING_ID_TO_CANCEL: [
               # MessageHandler(filters.TEXT & ~filters.COMMAND, process_cancel_booking),
               CallbackQueryHandler(confirm_and_delete_booking, pattern='^cancel_.*$')
            ],
            GET_BOOKING_ID_TO_PAYMENT: [
               CallbackQueryHandler(process_payment, pattern='^payment_.*$')
            ],
            CHOOSE_PAYMENT_METHOD: [
               CallbackQueryHandler(handle_payment_method_choice, pattern='^payment_method_.*$'),
               CallbackQueryHandler(handle_transfer_sent, pattern='^transfer_sent$')
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_booking, pattern='^cancel_booking$'),
            #CallbackQueryHandler(process_cancel_booking, pattern='^cancel_process$'),
            CommandHandler('start', start), # Позволяет пользователю начать заново с /s tart
        ],
        per_message=False # Позволяет вести несколько разговоров в одном чате, но с одним состоянием на пользователя
    )
    
    application.add_handler(booking_conv_handler)
    
    # Обработчик рассылки
    broadcast_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_menu_start, pattern='^broadcast_menu$')],
        states={
            BROADCAST_TYPE: [
                CallbackQueryHandler(broadcast_type_handler, pattern='^(broadcast_all|broadcast_selected|main_menu)$')
            ],
            BROADCAST_MESSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler),
                CommandHandler('cancel', broadcast_cancel_handler)
            ],
            BROADCAST_CONFIRM: [
                CallbackQueryHandler(broadcast_confirm_handler, pattern='^(broadcast_send|broadcast_cancel)$')
            ]
        },
        fallbacks=[CommandHandler('cancel', broadcast_cancel_handler)],
        per_message=False,
        per_user=True,
        allow_reentry=True
    )
    application.add_handler(broadcast_conv_handler)

    # Остальные обработчики
    application.add_handler(MessageHandler(filters.Regex('^🏠 Главное меню$'), main_menu_from_reply_button))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop_bot)) # Команда для остановки бота
    application.add_handler(CommandHandler("add_admin", add_admin)) # Добавление администратора
    application.add_handler(CommandHandler("remove_admin", remove_admin)) # Удаление администратора
    application.add_handler(CommandHandler("list_admins", list_admins)) # Список администраторов
    application.add_handler(CommandHandler("mybookings", my_bookings_handler)) # Новый обработчик
    application.add_handler(CallbackQueryHandler(my_bookings_handler, pattern='^my_bookings$')) # Новая кнопка
    application.add_handler(CallbackQueryHandler(admin_bookings_handler, pattern='^admin_bookings$')) # Кнопка администратора
    application.add_handler(CallbackQueryHandler(admin_bookings_handler, pattern='^admin_bookings_page_')) # Пагинация администратора
    
    # Обработчики для истории рассылок
    application.add_handler(CallbackQueryHandler(broadcast_history_handler, pattern='^broadcast_history$'))
    application.add_handler(CallbackQueryHandler(broadcast_history_handler, pattern='^broadcast_history_page_'))
    application.add_handler(CallbackQueryHandler(broadcast_resend_handler, pattern='^broadcast_resend_'))
    application.add_handler(CallbackQueryHandler(broadcast_resend_confirm_handler, pattern='^broadcast_resend_confirm_'))
    application.add_handler(CallbackQueryHandler(confirm_payment, pattern='^payment_confirmed$')) # Обработчик подтверждения оплаты
    application.add_handler(CallbackQueryHandler(handle_payment_method_choice, pattern='^payment_method_.*$')) # Обработчик выбора способа оплаты
    application.add_handler(CallbackQueryHandler(handle_transfer_sent, pattern='^transfer_sent$')) # Обработчик подтверждения перевода
    application.add_handler(CallbackQueryHandler(main_menu_callback, pattern='^main_menu$'))
    application.add_handler(CallbackQueryHandler(stop_bot_callback, pattern='^stop_bot$')) # Кнопка для остановки бота
    # main_menu_finish теперь используется ТОЛЬКО для выхода из ConversationHandler
    # application.add_handler(CallbackQueryHandler(main_menu_finish, pattern='^main_menu_finish$'))
    
    application.add_handler(CallbackQueryHandler(show_contacts, pattern='^contacts$'))
    application.add_handler(CallbackQueryHandler(mc_main_menu, pattern='^mc_main$'))
    application.add_handler(CallbackQueryHandler(exit_conversation_to_main_menu, pattern='^exit_conversation_to_main_menu$'))
    application.add_handler(CallbackQueryHandler(mc_programs, pattern='^mc_programs$'))
    application.add_handler(CallbackQueryHandler(mc_conditions, pattern='^mc_conditions$'))
    application.add_handler(CallbackQueryHandler(mc_book_start, pattern='^mc_book$'))
    application.add_handler(CallbackQueryHandler(mc_main_menu, pattern='^mc_back$'))
    application.add_handler(CallbackQueryHandler(shop_main_menu, pattern='^shop_main$'))
    application.add_handler(CallbackQueryHandler(shop_news, pattern='^shop_news$'))
    application.add_handler(CallbackQueryHandler(shop_order, pattern='^shop_order$'))
    application.add_handler(CallbackQueryHandler(tea_main_menu, pattern='^tea_main$'))
    application.add_handler(CallbackQueryHandler(tea_programs, pattern='^tea_programs$'))
    application.add_handler(CallbackQueryHandler(tea_conditions, pattern='^tea_conditions$'))
    
    # Обработчики для детальной информации о программах мастер-классов
    application.add_handler(CallbackQueryHandler(mc_chocolate_details, pattern='^mc_chocolate_details$'))
    application.add_handler(CallbackQueryHandler(mc_candy_details, pattern='^mc_candy_details$'))
    
    # Обработчики для детальной информации о программах чайной зоны
    application.add_handler(CallbackQueryHandler(tea_rent_details, pattern='^tea_rent_details$'))
    application.add_handler(CallbackQueryHandler(tea_ceremony_details, pattern='^tea_ceremony_details$'))
    application.add_handler(CallbackQueryHandler(tea_cacao_details, pattern='^tea_cacao_details$'))
    application.add_handler(CallbackQueryHandler(tea_self_chocolate_details, pattern='^tea_self_chocolate_details$'))
    application.add_handler(CallbackQueryHandler(tea_self_candy_details, pattern='^tea_self_candy_details$'))
    
    # Обработчики для бронирования из детальной информации программ
    application.add_handler(CallbackQueryHandler(mc_book_start, pattern='^mc_book_chocolate$'))
    application.add_handler(CallbackQueryHandler(mc_book_start, pattern='^mc_book_candy$'))
    application.add_handler(CallbackQueryHandler(tea_book_start, pattern='^tea_book_rent$'))
    application.add_handler(CallbackQueryHandler(tea_book_start, pattern='^tea_book_ceremony$'))
    application.add_handler(CallbackQueryHandler(tea_book_start, pattern='^tea_book_cacao$'))
    application.add_handler(CallbackQueryHandler(tea_book_start, pattern='^tea_book_self_chocolate$'))
    application.add_handler(CallbackQueryHandler(tea_book_start, pattern='^tea_book_self_candy$'))

    # Запуск веб-сервера для webhook в отдельном потоке
    webhook_app = Flask(__name__)
    
    @webhook_app.route('/webhook/payment', methods=['POST'])
    def payment_webhook():
        """Endpoint для приема webhook от платежной системы."""
        try:
            # Извлекаем данные из запроса
            data = request.get_json()
            
            if not data:
                return jsonify({'success': False, 'message': 'Нет данных'}), 400
            
            # Обрабатываем платеж
            result = process_payment_webhook(data)
            
            if result['success']:
                return jsonify(result), 200
            else:
                return jsonify(result), 400
                
        except Exception as e:
            logger.error(f"Ошибка в webhook endpoint: {e}")
            return jsonify({'success': False, 'message': f'Внутренняя ошибка: {str(e)}'}), 500
    
    @webhook_app.route('/health', methods=['GET'])
    def health_check():
        """Endpoint для проверки работоспособности сервера."""
        return jsonify({'status': 'ok', 'message': 'Webhook сервер работает'})
    
    # Запускаем webhook сервер в отдельном потоке
    def run_webhook_server():
        
        # Проверяем доступность порта 5000
        port = 5000
        max_attempts = 5
        
        for attempt in range(max_attempts):
            try:
                # Проверяем доступность порта
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(('', port))
                # Если порт свободен, запускаем Flask приложение
                logger.info(f"Webhook сервер запущен на порту {port}")
                webhook_app.run(host='0.0.0.0', port=port, debug=False)
                break
            except OSError as e:
                if e.errno == 98 or e.errno == 10048:  # Address already in use (Linux/Windows)
                    if attempt < max_attempts - 1:
                        port += 1
                        logger.warning(f"Порт {port-1} занят, пробую порт {port}...")
                        continue
                    else:
                        logger.error(f"Не удалось найти свободный порт после {max_attempts} попыток")
                        logger.info("Продолжаю работу без webhook сервера...")
                        return
                else:
                    logger.error(f"Ошибка при запуске webhook сервера: {e}")
                    return
    
    webhook_thread = threading.Thread(target=run_webhook_server, daemon=True)
    webhook_thread.start()
    
    # Запуск бота
    logger.info("🤖 Запускаем Telegram бота Royal Forest...")
    
    try:
        # Запускаем бота с обработкой KeyboardInterrupt для надежного завершения
        logger.info("🚀 Бот успешно запущен и работает...")
        application.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        try:
            safe_exit()
        except Exception as e:
            logger.error(f"Ошибка при безопасном завершении: {e}")
            immediate_exit()
    except Exception as e:
        logger.error(f"❌ Произошла ошибка при работе бота: {e}")
        logger.info("✅ Бот завершил работу.")
        os._exit(1)

if __name__ == '__main__':
    main()