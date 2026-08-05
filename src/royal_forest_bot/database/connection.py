"""Database connection and session management."""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base

from ..config.settings import settings
from ..config.logging_config import get_logger

logger = get_logger(__name__)


# Глобальный движок БД
_engine: AsyncEngine | None = None

# Фабрика сессий
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def create_db_engine(database_url: str | None = None) -> AsyncEngine:
    """
    Создание асинхронного движка базы данных.
    
    Args:
        database_url: URL подключения к БД (по умолчанию из настроек)
        
    Returns:
        AsyncEngine экземпляр движка
    """
    global _engine
    
    if database_url is None:
        database_url = settings.database_url
    
    logger.info("Создание движка базы данных", url=database_url)
    
    _engine = create_async_engine(
        database_url,
        echo=False,  # Установить True для отладки SQL запросов
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    
    return _engine


def get_engine() -> AsyncEngine:
    """Получение текущего движка БД."""
    if _engine is None:
        raise RuntimeError("Движок БД не инициализирован. Вызовите create_db_engine()")
    return _engine


async def init_db() -> None:
    """
    Инициализация базы данных - создание таблиц.
    """
    from .models import Base
    
    engine = get_engine()
    
    logger.info("Инициализация базы данных, создание таблиц")
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("База данных успешно инициализирована")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Получение асинхронной сессии БД.
    
    Yields:
        AsyncSession сессия базы данных
    """
    global _async_session_maker
    
    if _async_session_maker is None:
        if _engine is None:
            raise RuntimeError("Движок БД не инициализирован")
        
        _async_session_maker = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    
    async with _async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db() -> None:
    """Закрытие соединения с базой данных."""
    global _engine, _async_session_maker
    
    if _engine is not None:
        logger.info("Закрытие соединения с базой данных")
        await _engine.dispose()
        _engine = None
        _async_session_maker = None
