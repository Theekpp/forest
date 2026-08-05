# 🌲 Royal Forest Telegram Bot

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code Style](https://img.shields.io/badge/code%20style-ruff-black)](https://github.com/astral-sh/ruff)
[![Type Checking](https://img.shields.io/badge/type%20checking-mypy-blue)](https://mypy.readthedocs.io/)

Telegram-бот для автоматизации бронирования услуг компании **Royal Forest**. Предназначен для записи клиентов на программы отдыха, управления бронированиями и взаимодействия с администраторами.

## 📋 Содержание

- [О проекте](#-о-проекте)
- [Возможности](#-возможности)
- [Архитектура](#-архитектура)
- [Требования](#-требования)
- [Установка](#-установка)
- [Конфигурация](#-конфигурация)
- [Запуск](#-запуск)
- [Использование](#-использование)
- [Структура проекта](#-структура-проекта)
- [Разработка](#-разработка)
- [Тестирование](#-тестирование)
- [Деплой](#-деплой)
- [Troubleshooting](#-troubleshooting)
- [Лицензия](#-лицензия)
- [Контакты](#-контакты)

---

## 🎯 О проекте

**Royal Forest Bot** — это современное решение для автоматизации процесса бронирования услуг в сфере hospitality. Бот предоставляет интуитивно понятный интерфейс для клиентов и мощные инструменты управления для администраторов.

### Ключевые преимущества

- ✅ **Автоматизация** — сокращение ручного труда администраторов
- ✅ **Доступность 24/7** — клиенты могут бронировать в любое время
- ✅ **Прозрачность** — полная история бронирований и рассылок
- ✅ **Масштабируемость** — архитектура поддерживает рост нагрузки
- ✅ **Безопасность** — разграничение прав доступа и защита данных

---

## ✨ Возможности

### Для клиентов

- 📅 **Бронирование программ** — выбор даты, времени и количества участников
- 📋 **Просмотр активных бронирований** — история и статусы записей
- ❌ **Отмена бронирования** — возможность отмены с проверкой условий
- 💳 **Информация об оплате** — отображение стоимости и предоплаты
- 🔔 **Уведомления** — подтверждения и напоминания о бронированиях

### Для администраторов

- 👥 **Управление пользователями** — просмотр списка клиентов, блокировка
- 📊 **Мониторинг бронирований** — все записи с фильтрацией и пагинацией
- 📢 **Рассылки** — массовые уведомления по различным критериям
- ⚙️ **Настройка статусов** — подтверждение, отмена, изменение параметров
- 🛡️ **Безопасность** — защита админ-функций паролем

### Технические особенности

- 🔄 **Асинхронная архитектура** — высокая производительность
- 💾 **SQLite + SQLAlchemy** — надежное хранение данных
- 📝 **Структурированное логирование** — easy debugging через structlog
- 🔧 **Гибкая конфигурация** — управление через переменные окружения
- 🧪 **Тестируемость** — покрытие unit и integration тестами

---

## 🏗️ Архитектура

Проект построен по принципам **Clean Architecture** с соблюдением SOLID:

```
┌─────────────────────────────────────────────────────────┐
│                   Infrastructure Layer                   │
│  (Telegram Client, Webhooks, Console, Database Engine)   │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                  Application Layer                       │
│        (Handlers, Keyboards, Filters, Middlewares)       │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                    Domain Layer                          │
│           (Entities, Services, Business Logic)           │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                 Database Layer                           │
│              (Repositories, Models, ORM)                 │
└──────────────────────────────────────────────────────────┘
```

### Слои архитектуры

| Слой | Ответственность | Компоненты |
|------|----------------|------------|
| **Infrastructure** | Внешние зависимости | Telegram Bot API, Flask webhooks, Console monitor |
| **Application** | Бизнес-процессы | Обработчики команд, клавиатуры, фильтры, middleware |
| **Domain** | Бизнес-логика | Сущности (entities), сервисы, правила предметной области |
| **Database** | Хранение данных | SQLAlchemy модели, репозитории, миграции |

### Принципы проектирования

- **SOLID** — все 5 принципов объектно-ориентированного дизайна
- **DRY** — исключение дублирования кода
- **KISS** — сохранение простоты решений
- **Separation of Concerns** — разделение ответственности между модулями
- **Dependency Injection** — внедрение зависимостей для тестируемости
- **Async-first** — приоритет асинхронных операций

---

## 📦 Требования

### Обязательные

- **Python**: 3.10 или выше
- **PostgreSQL**: 12+ (или SQLite для разработки)
- **Telegram Bot Token**: получите у [@BotFather](https://t.me/BotFather)

### Опциональные

- **Docker**: 20+ для контейнеризации
- **Docker Compose**: для оркестрации сервисов

---

## 🚀 Установка

### Вариант 1: Локальная установка (рекомендуется для разработки)

#### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd royal_forest_bot
```

#### 2. Создание виртуального окружения

```bash
# Linux/macOS
python -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
venv\Scripts\activate
```

#### 3. Установка зависимостей

```bash
# Основные зависимости
pip install -e .

# Зависимости для разработки (опционально)
pip install -e ".[dev]"
```

#### 4. Настройка переменных окружения

```bash
# Скопируйте шаблон
cp .env.example .env

# Отредактируйте .env файл
nano .env  # или используйте любой редактор
```

### Вариант 2: Docker (для production)

```bash
# Сборка образа
docker-compose build

# Запуск сервисов
docker-compose up -d
```

---

## ⚙️ Конфигурация

### Переменные окружения

Создайте файл `.env` в корне проекта на основе `.env.example`:

| Переменная | Описание | Пример | Обязательно |
|------------|----------|--------|-------------|
| `TELEGRAM_TOKEN` | Токен Telegram бота | `123456:ABC-DEF...` | ✅ |
| `ADMIN_IDS` | ID администраторов (через запятую) | `730318118,123456789` | ✅ |
| `CONSOLE_PASSWORD` | Пароль для консольной остановки | `admin123` | ✅ |
| `MAX_PASSWORD_ATTEMPTS` | Максимум попыток ввода пароля | `3` | ❌ |
| `BLOCK_TIME_SECONDS` | Время блокировки (сек) | `300` | ❌ |
| `DB_NAME` | Имя файла базы данных | `bookings.db` | ❌ |
| `DATABASE_URL` | URL подключения к БД | `sqlite+aiosqlite:///bookings.db` | ❌ |
| `WEBHOOK_PORT` | Порт webhook сервера | `5000` | ❌ |
| `LOG_LEVEL` | Уровень логирования | `INFO`, `DEBUG`, `WARNING` | ❌ |

### Пример .env файла

```bash
# Telegram Bot Token (получите у @BotFather)
TELEGRAM_TOKEN=your_bot_token_here

# Telegram ID администраторов (через запятую)
ADMIN_IDS=730318118

# Пароль для консольной остановки
CONSOLE_PASSWORD=admin123

# Максимальное количество попыток ввода пароля
MAX_PASSWORD_ATTEMPTS=3

# Время блокировки в секундах после неудачных попыток (5 минут)
BLOCK_TIME_SECONDS=300

# Имя файла базы данных
DB_NAME=bookings.db

# Порт для webhook сервера
WEBHOOK_PORT=5000

# Уровень логирования
LOG_LEVEL=INFO
```

---

## ▶️ Запуск

### Режим разработки

```bash
# Активация виртуального окружения
source venv/bin/activate

# Запуск бота
python -m src.royal_forest_bot.main
```

### Production режим

```bash
# С использованием gunicorn (для webhook)
gunicorn "src.royal_forest_bot.infrastructure.webhooks:create_app()" \
    --bind 0.0.0.0:5000 \
    --workers 4 \
    --access-logfile logs/access.log \
    --error-logfile logs/error.log
```

### Docker Compose

```bash
# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f bot

# Остановка
docker-compose down
```

---

## 💡 Использование

### Команды бота

| Команда | Описание | Доступ |
|---------|----------|--------|
| `/start` | Запуск бота, главное меню | Все |
| `/help` | Справка по командам | Все |
| `/book` | Начать бронирование | Все |
| `/mybookings` | Мои бронирования | Все |
| `/cancel` | Отмена текущего действия | Все |
| `/admin` | Админ-панель | Админы |
| `/broadcast` | Рассылка сообщений | Админы |
| `/users` | Список пользователей | Админы |
| `/stop` | Остановка бота (консоль) | Админы |

### Сценарии использования

#### Бронирование для клиента

1. Пользователь отправляет `/start` или нажимает «Забронировать»
2. Выбирает программу из предложенных вариантов
3. Указывает желаемую дату и время
4. Вводит количество участников
5. Предоставляет контактные данные (имя, телефон)
6. Получает подтверждение с деталями бронирования

#### Управление бронированиями для администратора

1. Администратор входит через `/admin`
2. Вводит пароль для подтверждения прав
3. Получает доступ к функциям:
   - Просмотр всех бронирований
   - Подтверждение/отмена записей
   - Фильтрация по датам и статусам
   - Экспорт данных

#### Рассылка уведомлений

1. Администратор выбирает `/broadcast`
2. Определяет целевую аудиторию (все, по статусу, по дате)
3. Вводит текст сообщения
4. Подтверждает отправку
5. Получает отчет о результатах рассылки

---

## 📁 Структура проекта

```
royal_forest_bot/
├── README.md                    # Документация (этот файл)
├── ARCHITECTURE.md              # Подробное описание архитектуры
├── pyproject.toml               # Конфигурация проекта и зависимости
├── .env.example                 # Шаблон переменных окружения
├── .gitignore                   # Исключения для git
├── docker-compose.yml           # Оркестрация Docker-контейнеров
├── Dockerfile                   # Инструкция сборки Docker-образа
│
└── src/
    └── royal_forest_bot/
        ├── __init__.py          # Пакет проекта
        ├── main.py              # Точка входа приложения
        │
        ├── config/              # Конфигурация
        │   ├── __init__.py
        │   ├── settings.py      # Pydantic настройки
        │   └── logging_config.py # Конфигурация логирования
        │
        ├── core/                # Ядро приложения
        │   ├── __init__.py
        │   ├── exceptions.py    # Кастомные исключения
        │   ├── constants.py     # Константы и перечисления
        │   └── security.py      # Функции безопасности
        │
        ├── database/            # Работа с данными
        │   ├── __init__.py
        │   ├── connection.py    # Подключение к БД
        │   ├── models.py        # SQLAlchemy модели
        │   └── repositories/    # Репозитории
        │       ├── __init__.py
        │       ├── base.py      # Базовый репозиторий
        │       ├── users.py     # Пользователи
        │       ├── bookings.py  # Бронирования
        │       └── broadcasts.py # Рассылки
        │
        ├── domain/              # Бизнес-логика
        │   ├── __init__.py
        │   ├── entities/        # Доменные сущности
        │   │   ├── user.py
        │   │   ├── booking.py
        │   │   └── broadcast.py
        │   └── services/        # Сервисы
        │       ├── booking_service.py
        │       ├── user_service.py
        │       ├── broadcast_service.py
        │       └── payment_service.py
        │
        ├── application/         # Прикладной слой
        │   ├── handlers/        # Обработчики Telegram
        │   │   ├── common.py    # /start, /help
        │   │   ├── booking.py   # Бронирование
        │   │   ├── admin.py     # Админ-функции
        │   │   └── broadcast.py # Рассылки
        │   ├── keyboards/       # Клавиатуры
        │   │   ├── main_menu.py
        │   │   ├── booking_menu.py
        │   │   └── admin_menu.py
        │   ├── filters/         # Фильтры сообщений
        │   │   ├── admin.py
        │   │   └── booking.py
        │   └── middlewares/     # Middleware
        │       ├── logging.py
        │       ├── database.py
        │       └── throttling.py
        │
        ├── infrastructure/      # Инфраструктура
        │   ├── telegram/        # Telegram клиент
        │   ├── webhooks/        # Webhook обработчики
        │   └── console/         # Консольный мониторинг
        │
        └── utils/               # Утилиты
            ├── formatters.py    # Форматирование
            ├── validators.py    # Валидация
            └── helpers.py       # Вспомогательные функции
```

---

## 🛠️ Разработка

### Установка dev-зависимостей

```bash
pip install -e ".[dev]"
```

### Инструменты разработки

| Инструмент | Назначение | Команда |
|------------|------------|---------|
| **ruff** | Линтер и форматтер | `ruff check . && ruff format .` |
| **mypy** | Проверка типов | `mypy src/` |
| **pytest** | Тестирование | `pytest tests/` |
| **pre-commit** | Git хуки | `pre-commit install` |

### Pre-commit хуки

Настройте автоматические проверки перед коммитом:

```bash
# Установка pre-commit
pip install pre-commit
pre-commit install

# Запуск всех хуков вручную
pre-commit run --all-files
```

### Соглашения по коду

- **Именование**: snake_case для функций/переменных, PascalCase для классов
- **Docstrings**: Google style для всех публичных методов
- **Типизация**: Полная аннотация типов (type hints)
- **Длина строки**: максимум 100 символов
- **Импорты**: Сортировка через isort (автоматически через ruff)

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты
pytest

# С покрытием
pytest --cov=src.royal_forest_bot --cov-report=html

# Конкретный файл
pytest tests/test_booking_service.py

# С выводом логов
pytest -s -v
```

### Структура тестов

```
tests/
├── __init__.py
├── conftest.py              # Фикстуры pytest
├── unit/
│   ├── test_booking_entity.py
│   ├── test_booking_service.py
│   └── test_user_service.py
├── integration/
│   ├── test_booking_flow.py
│   └── test_broadcast.py
└── e2e/
    └── test_user_journey.py
```

### Фикстуры

Основные фикстуры доступны в `conftest.py`:

- `async_session` — асинхронная сессия БД
- `booking_service` — сервис бронирований
- `test_user` — тестовый пользователь
- `mock_telegram_bot` — мок Telegram бота

---

## 🚢 Деплой

### Docker Compose (Production)

Создайте `docker-compose.yml`:

```yaml
version: '3.8'

services:
  bot:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    networks:
      - royal_forest_net
    depends_on:
      - db

  db:
    image: postgres:15-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: royal_forest
      POSTGRES_USER: ${DB_USER:-bot}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-secure_password}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - royal_forest_net

  webhook:
    build: .
    command: gunicorn "src.royal_forest_bot.infrastructure.webhooks:create_app()" \
             --bind 0.0.0.0:5000 --workers 4
    restart: unless-stopped
    env_file: .env
    ports:
      - "5000:5000"
    networks:
      - royal_forest_net
    depends_on:
      - db

networks:
  royal_forest_net:
    driver: bridge

volumes:
  postgres_data:
```

### Переменные окружения для production

```bash
# .env.production
TELEGRAM_TOKEN=your_production_token
ADMIN_IDS=730318118
CONSOLE_PASSWORD=<strong_password>
DATABASE_URL=postgresql+asyncpg://bot:secure_password@db:5432/royal_forest
LOG_LEVEL=WARNING
```

### CI/CD Pipeline (GitHub Actions)

Пример `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v4
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Lint with ruff
        run: ruff check .

      - name: Type check with mypy
        run: mypy src/

      - name: Test with pytest
        run: pytest --cov=src.royal_forest_bot

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v3

      - name: Deploy to server
        run: |
          # Ваш скрипт деплоя
          echo "Deploying..."
```

---

## 🔧 Troubleshooting

### Частые проблемы

#### 1. Бот не отвечает на команды

**Причина**: Неправильный токен или проблемы с подключением

**Решение**:
```bash
# Проверьте токен
echo $TELEGRAM_TOKEN

# Проверьте логи
tail -f logs/bot.log

# Перезапустите бота
docker-compose restart bot
```

#### 2. Ошибки базы данных

**Причина**: Отсутствие миграций или повреждение БД

**Решение**:
```bash
# Для SQLite - удалите и создайте заново
rm bookings.db
python -m src.royal_forest_bot.main  # Таблицы создадутся автоматически

# Для PostgreSQL - примените миграции
alembic upgrade head
```

#### 3. Webhook не работает

**Причина**: Порт занят или недоступен извне

**Решение**:
```bash
# Проверьте порт
netstat -tlnp | grep 5000

# Проверьте firewall
sudo ufw status

# Настройте webhook в Telegram
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://your-domain.com:5000/webhook"
```

#### 4. Проблемы с правами администратора

**Причина**: ADMIN_IDS не настроен или неверный формат

**Решение**:
```bash
# Узнайте свой Telegram ID через @userinfobot
# Обновите .env
ADMIN_IDS=your_id,other_admin_id

# Перезапустите бота
```

### Логи

Логи находятся в директории `logs/`:

- `bot.log` — основные логи бота
- `access.log` — логи доступа (webhook)
- `error.log` — ошибки приложения

Просмотр в реальном времени:
```bash
tail -f logs/bot.log
```

---

## 📄 Лицензия

Этот проект распространяется под лицензией MIT. См. файл [LICENSE](LICENSE) для деталей.

---

## 🙏 Благодарности

- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) — отличная библиотека для Telegram ботов
- [SQLAlchemy](https://www.sqlalchemy.org/) — мощный ORM инструмент
- [Pydantic](https://docs.pydantic.dev/) — валидация данных и настройки
- [Structlog](https://www.structlog.org/) — структурированное логирование

---

## 📈 Roadmap

- [ ] Интеграция платежных систем (ЮKassa, CloudPayments)
- [ ] Мультиязычность (i18n)
- [ ] Веб-панель администратора
- [ ] Аналитика и отчеты
- [ ] Интеграция с CRM
- [ ] Push-уведомления
- [ ] Календарь занятости
- [ ] Система лояльности

---

<div align="center">

**Made with ❤️ by Royal Forest Team (Theekpp)**

[⬆️ Вернуться к началу](#-royal-forest-telegram-bot)

</div>
