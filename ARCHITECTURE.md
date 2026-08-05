# 🏗️ Архитектура проекта Telegram-бота "Royal Forest"

## 📋 Анализ текущего состояния

### Текущая структура
- **Один файл**: `last_with_sql.py` (3382 строки)
- **Монолитная архитектура**: весь код в одном файле
- **Смешанные ответственности**: бизнес-логика, UI, БД, API перемешаны

### Выявленные проблемы
1. ❌ Нарушение Single Responsibility Principle
2. ❌ Глобальные переменные (`application`, `ADMIN_IDS`, `failed_attempts`)
3. ❌ Прямые SQL-запросы без ORM/слоя абстракции
4. ❌ Отсутствие типизации
5. ❌ Дублирование кода (особенно в обработчиках меню)
6. ❌ Сложность тестирования
7. ❌ Отсутствие конфигурационного менеджера
8. ❌ Смешение синхронного и асинхронного кода

---

## 🎯 Целевая архитектура

### Принципы проектирования
- **SOLID** - все 5 принципов
- **DRY** - не повторяйся
- **KISS** -保持简单
- **Separation of Concerns** - разделение ответственности
- **Dependency Injection** - внедрение зависимостей
- **Async-first** - приоритет асинхронности

### Структура проекта

```
royal_forest_bot/
├── README.md
├── pyproject.toml              # Современная упаковка проекта
├── .env.example                # Шаблон переменных окружения
├── .gitignore
├── docker-compose.yml          # Оркестрация сервисов
├── Dockerfile
└── src/
    └── royal_forest_bot/
        ├── __init__.py
        ├── main.py             # Точка входа
        │
        ├── config/
        │   ├── __init__.py
        │   ├── settings.py     # Настройки через pydantic-settings
        │   └── logging_config.py
        │
        ├── core/
        │   ├── __init__.py
        │   ├── exceptions.py   # Кастомные исключения
        │   ├── constants.py    # Константы состояний
        │   └── security.py     # Безопасность (пароли, блокировки)
        │
        ├── database/
        │   ├── __init__.py
        │   ├── connection.py   # Подключение к БД
        │   ├── models.py       # SQLAlchemy модели
        │   ├── repositories/
        │   │   ├── __init__.py
        │   │   ├── base.py     # Базовый репозиторий
        │   │   ├── users.py    # Пользователи
        │   │   ├── bookings.py # Бронирования
        │   │   └── broadcasts.py # Рассылки
        │   └── migrations/     # Миграции Alembic
        │
        ├── domain/
        │   ├── __init__.py
        │   ├── entities/       # Бизнес-объекты
        │   │   ├── user.py
        │   │   ├── booking.py
        │   │   └── broadcast.py
        │   └── services/       # Бизнес-логика
        │       ├── __init__.py
        │       ├── booking_service.py
        │       ├── user_service.py
        │       ├── broadcast_service.py
        │       └── payment_service.py
        │
        ├── application/
        │   ├── __init__.py
        │   ├── handlers/       # Обработчики Telegram
        │   │   ├── __init__.py
        │   │   ├── common.py   # Общие команды (/start, /help)
        │   │   ├── booking.py  # Бронирование
        │   │   ├── admin.py    # Админ-функции
        │   │   ├── payment.py  # Платежи
        │   │   └── broadcast.py # Рассылки
        │   ├── keyboards/      # Клавиатуры
        │   │   ├── __init__.py
        │   │   ├── main_menu.py
        │   │   ├── booking_menu.py
        │   │   ├── admin_menu.py
        │   │   └── inline_menus.py
        │   ├── filters/        # Фильтры сообщений
        │   │   ├── __init__.py
        │   │   ├── admin.py
        │   │   └── booking.py
        │   └── middlewares/    # Middleware
        │       ├── __init__.py
        │       ├── logging.py
        │       ├── database.py
        │       └── throttling.py
        │
        ├── infrastructure/
        │   ├── __init__.py
        │   ├── telegram/       # Telegram клиент
        │   │   └── bot.py
        │   ├── webhooks/       # Webhook обработчики
        │   │   ├── __init__.py
        │   │   └── payment.py
        │   └── console/        # Консольный мониторинг
        │       └── monitor.py
        │
        └── utils/
            ├── __init__.py
            ├── formatters.py   # Форматирование текста
            ├── validators.py   # Валидация данных
            └── helpers.py      # Вспомогательные функции
```

---

## 📦 Зависимости (pyproject.toml)

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "royal-forest-bot"
version = "2.0.0"
description = "Telegram бот для бронирования услуг Royal Forest"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "python-telegram-bot>=21.0",
    "sqlalchemy>=2.0",
    "aiosqlite>=0.19",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "alembic>=1.13",
    "flask>=3.0",
    "python-dotenv>=1.0",
    "structlog>=24.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "ruff>=0.3",
    "mypy>=1.8",
    "pre-commit>=3.6",
]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.mypy]
python_version = "3.10"
strict = true
```

---

## 🔧 Ключевые компоненты

### 1. Конфигурация (config/settings.py)

```python
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Telegram
    telegram_token: str
    admin_ids: List[int] = [730318118]
    
    # Database
    db_name: str = "bookings.db"
    database_url: str = "sqlite+aiosqlite:///bookings.db"
    
    # Security
    console_password: str = "admin123"
    max_password_attempts: int = 3
    block_time_seconds: int = 300
    
    # Webhook
    webhook_port: int = 5000
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
```

### 2. Модели базы данных (database/models.py)

```python
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    
    user_id = Column(Integer, primary_key=True)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    is_blocked = Column(Boolean, default=False)
    last_activity = Column(DateTime, default=datetime.utcnow)
    registered_at = Column(DateTime, default=datetime.utcnow)


class Booking(Base):
    __tablename__ = "bookings"
    
    booking_id = Column(String, primary_key=True)
    user_id = Column(Integer, nullable=False)
    program = Column(String, nullable=False)
    date = Column(String, nullable=False)
    time = Column(String, nullable=False)
    people = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    cost = Column(Float, nullable=False)
    prepayment = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)


class BroadcastHistory(Base):
    __tablename__ = "broadcast_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, nullable=False)
    admin_username = Column(String)
    admin_name = Column(String)
    broadcast_type = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    target_users = Column(String)  # JSON
    total_sent = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)
    total_blocked = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
```

### 3. Репозитории (database/repositories/bookings.py)

```python
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from ...domain.entities.booking import BookingEntity
from ...database.models import Booking


class BookingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, booking: BookingEntity) -> Booking:
        db_booking = Booking(**booking.dict())
        self.session.add(db_booking)
        await self.session.commit()
        await self.session.refresh(db_booking)
        return db_booking
    
    async def get_by_id(self, booking_id: str) -> Optional[Booking]:
        result = await self.session.execute(
            select(Booking).where(Booking.booking_id == booking_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_user_id(self, user_id: int) -> List[Booking]:
        result = await self.session.execute(
            select(Booking).where(Booking.user_id == user_id)
        )
        return result.scalars().all()
    
    async def update_status(self, booking_id: str, status: str) -> bool:
        stmt = update(Booking).where(
            Booking.booking_id == booking_id
        ).values(status=status)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0
    
    async def delete(self, booking_id: str) -> bool:
        stmt = delete(Booking).where(Booking.booking_id == booking_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0
```

### 4. Бизнес-сервисы (domain/services/booking_service.py)

```python
from typing import List, Optional
from datetime import datetime
import uuid

from ...domain.entities.booking import BookingEntity
from ...database.repositories.bookings import BookingRepository


class BookingService:
    def __init__(self, booking_repo: BookingRepository):
        self.booking_repo = booking_repo
    
    async def create_booking(self, data: dict) -> BookingEntity:
        booking = BookingEntity(
            booking_id=str(uuid.uuid4()),
            user_id=data["user_id"],
            program=data["program"],
            date=data["date"],
            time=data["time"],
            people=data["people"],
            name=data["name"],
            phone=data["phone"],
            cost=data["cost"],
            prepayment=data["prepayment"],
            status="pending",
            timestamp=datetime.utcnow()
        )
        return await self.booking_repo.create(booking)
    
    async def cancel_booking(self, booking_id: str) -> bool:
        return await self.booking_repo.update_status(booking_id, "cancelled")
    
    async def get_user_bookings(self, user_id: int) -> List[BookingEntity]:
        bookings = await self.booking_repo.get_by_user_id(user_id)
        return [BookingEntity.from_orm(b) for b in bookings]
```

### 5. Обработчики (application/handlers/booking.py)

```python
from telegram import Update
from telegram.ext import ConversationHandler, CommandHandler, CallbackQueryHandler

from ...application.keyboards.booking_menu import BookingKeyboardBuilder
from ...domain.services.booking_service import BookingService


class BookingHandler:
    def __init__(self, booking_service: BookingService):
        self.booking_service = booking_service
        self.keyboard_builder = BookingKeyboardBuilder()
    
    def register_handlers(self, application) -> None:
        conv_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.start_booking, pattern='^mc_book$'),
                CallbackQueryHandler(self.start_booking, pattern='^tea_book_start$'),
            ],
            states={
                CHOOSE_PROGRAM: [
                    CallbackQueryHandler(self.choose_program),
                ],
                CHOOSE_DATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.choose_date),
                ],
                # ... остальные состояния
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )
        application.add_handler(conv_handler)
    
    async def start_booking(self, update: Update, context) -> int:
        # Логика начала бронирования
        pass
```

### 6. Точка входа (main.py)

```python
import asyncio
import signal
import logging

from telegram.ext import Application

from .config.settings import settings
from .config.logging_config import setup_logging
from .database.connection import create_db_engine, init_db
from .domain.services.booking_service import BookingService
from .domain.services.user_service import UserService
from .application.handlers.booking import BookingHandler
from .application.handlers.admin import AdminHandler
from .infrastructure.telegram.bot import BotWrapper


logger = logging.getLogger(__name__)


def create_application() -> Application:
    """Factory для создания приложения"""
    return (
        Application.builder()
        .token(settings.telegram_token)
        .build()
    )


async def shutdown(app: Application) -> None:
    """Graceful shutdown"""
    logger.info("🛑 Завершение работы...")
    await app.stop()
    await app.shutdown()


def main() -> None:
    """Точка входа"""
    setup_logging()
    
    # Инициализация БД
    engine = create_db_engine(settings.database_url)
    init_db(engine)
    
    # Создание сервисов
    booking_service = BookingService(...)
    user_service = UserService(...)
    
    # Создание приложения
    app = create_application()
    
    # Регистрация обработчиков
    BookingHandler(booking_service).register_handlers(app)
    AdminHandler(user_service).register_handlers(app)
    
    # Graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(app)))
    
    # Запуск
    logger.info("🚀 Запуск бота Royal Forest...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
```

---

## 🔄 Миграция с текущей версии

### Этап 1: Подготовка (неделя 1)
- [ ] Создать структуру директорий
- [ ] Настроить pyproject.toml и зависимости
- [ ] Перенести конфигурацию в pydantic-settings
- [ ] Настроить логирование через structlog

### Этап 2: База данных (неделя 2)
- [ ] Создать SQLAlchemy модели
- [ ] Реализовать репозитории
- [ ] Настроить Alembic миграции
- [ ] Переписать функции БД на async

### Этап 3: Бизнес-логика (неделя 3)
- [ ] Выделить доменные сущности
- [ ] Создать сервисы
- [ ] Реализовать валидацию данных

### Этап 4: Обработчики (неделя 4)
- [ ] Рефакторинг обработчиков
- [ ] Выделить клавиатуры в отдельные классы
- [ ] Добавить фильтры и middleware

### Этап 5: Инфраструктура (неделя 5)
- [ ] Вынести webhook в отдельный модуль
- [ ] Рефакторинг консольного монитора
- [ ] Добавить health checks

### Этап 6: Тестирование и деплой (неделя 6)
- [ ] Написать unit-тесты
- [ ] Написать integration-тесты
- [ ] Создать Dockerfile и docker-compose
- [ ] Настроить CI/CD

---

## ✅ Преимущества новой архитектуры

| Аспект | Было | Стало |
|--------|------|-------|
| **Поддерживаемость** | Низкая (монолит) | Высокая (модульная) |
| **Тестируемость** | Практически нет | Полное покрытие тестами |
| **Масштабируемость** | Ограничена | Горизонтальное масштабирование |
| **Безопасность** | Глобальные переменные | DI и инкапсуляция |
| **Расширяемость** | Сложно добавлять | Легко добавлять модули |
| **Читаемость** | 3382 строки в одном файле | Логическое разделение |

---

## 📝 Рекомендации

1. **Начните с малого**: Сначала вынесите конфигурацию и БД
2. **Пишите тесты**: Покрытие > 80% для критических путей
3. **Используйте type hints**: Mypy поможет найти ошибки
4. **Документируйте**: Docstrings для всех публичных методов
5. **CI/CD**: Автоматизируйте тестирование и деплой
