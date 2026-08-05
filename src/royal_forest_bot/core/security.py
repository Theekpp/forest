"""Security utilities for console access and password management."""

import time
from typing import Optional
from dataclasses import dataclass, field

from ..config.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class SecurityState:
    """Состояние безопасности для консольного доступа."""

    failed_attempts: int = 0
    blocked_until: float = 0.0
    
    def is_blocked(self) -> bool:
        """Проверяет, заблокирован ли доступ."""
        if self.blocked_until > 0 and time.time() < self.blocked_until:
            return True
        # Сброс блокировки после истечения времени
        if self.blocked_until > 0 and time.time() >= self.blocked_until:
            self.reset()
        return False
    
    def get_remaining_block_time(self) -> int:
        """Возвращает оставшееся время блокировки в секундах."""
        if self.blocked_until > 0:
            remaining = int(self.blocked_until - time.time())
            return max(0, remaining)
        return 0
    
    def record_failed_attempt(self, max_attempts: int, block_time: int) -> bool:
        """
        Регистрирует неудачную попытку ввода пароля.
        
        Returns:
            True если достигнут лимит попыток и доступ заблокирован
        """
        self.failed_attempts += 1
        logger.warning(
            "Неудачная попытка ввода пароля",
            attempt=self.failed_attempts,
            max_attempts=max_attempts
        )
        
        if self.failed_attempts >= max_attempts:
            self.blocked_until = time.time() + block_time
            logger.error(
                f"Консоль заблокирована на {block_time // 60} минут",
                reason="Превышение попыток"
            )
            return True
        return False
    
    def reset(self) -> None:
        """Сбрасывает счетчик попыток и блокировку."""
        self.failed_attempts = 0
        self.blocked_until = 0.0
        logger.info("Счетчик неудачных попыток сброшен")


# Глобальное состояние безопасности
security_state = SecurityState()


def verify_password(input_password: str, correct_password: str) -> bool:
    """
    Проверяет пароль.
    
    Args:
        input_password: Введенный пароль
        correct_password: Правильный пароль
        
    Returns:
        True если пароль верный
    """
    return input_password == correct_password


def is_admin(user_id: int, admin_ids: list[int]) -> bool:
    """
    Проверяет, является ли пользователь администратором.
    
    Args:
        user_id: ID пользователя Telegram
        admin_ids: Список ID администраторов
        
    Returns:
        True если пользователь администратор
    """
    return user_id in admin_ids
