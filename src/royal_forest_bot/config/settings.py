"""Application settings using pydantic-settings."""

from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Настройки приложения из переменных окружения."""

    # Telegram
    telegram_token: str = Field(..., description="Telegram бот токен")
    
    # Admins
    admin_ids: List[int] = Field(
        default=[730318118],
        description="Список Telegram ID администраторов"
    )
    
    # Security
    console_password: str = Field(
        default="admin123",
        description="Пароль для консольной остановки"
    )
    max_password_attempts: int = Field(
        default=3,
        description="Максимальное количество попыток ввода пароля"
    )
    block_time_seconds: int = Field(
        default=300,
        description="Время блокировки в секундах после неудачных попыток"
    )
    
    # Database
    db_name: str = Field(
        default="bookings.db",
        description="Имя файла базы данных SQLite"
    )
    database_url: str = Field(
        default="sqlite+aiosqlite:///bookings.db",
        description="URL подключения к базе данных"
    )
    
    # Webhook
    webhook_port: int = Field(
        default=5000,
        description="Порт для webhook сервера"
    )
    
    # Logging
    log_level: str = Field(
        default="INFO",
        description="Уровень логирования"
    )
    
    class Config:
        """Конфигурация pydantic."""
        
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


# Глобальный экземпляр настроек
settings = Settings()
