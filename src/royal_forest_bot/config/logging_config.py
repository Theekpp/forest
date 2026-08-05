"""Logging configuration using structlog."""

import logging
import sys
from typing import Any

import structlog
from structlog.typing import Processor


def setup_logging(log_level: str = "INFO") -> None:
    """
    Настройка логирования с использованием structlog.
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Конфигурация стандартного logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )
    
    # Отключение логов httpx (как в оригинальном коде)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # Настройка structlog
    structlog.configure(
        processors=[
            # Добавление временной метки
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            
            # Обработка исключений
            structlog.processors.ExceptionPrettyPrinter(),
            
            # Форматирование для консоли
            structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """
    Получение логгера с именем.
    
    Args:
        name: Имя логгера (обычно __name__)
        
    Returns:
        Настроенный логгер structlog
    """
    return structlog.get_logger(name)
