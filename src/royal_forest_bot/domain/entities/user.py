"""User domain entity."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class UserEntity:
    """Бизнес-объект пользователя."""

    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_blocked: bool = False
    last_activity: Optional[datetime] = None
    registered_at: Optional[datetime] = None

    @property
    def full_name(self) -> str:
        """Полное имя пользователя."""
        parts = [self.first_name, self.last_name]
        return " ".join(filter(None, parts)) or self.username or f"User {self.user_id}"

    @property
    def mention(self) -> str:
        """Упоминание пользователя в Telegram."""
        if self.username:
            return f"@{self.username}"
        return self.full_name

    def is_active(self) -> bool:
        """Проверка активности пользователя."""
        return not self.is_blocked

    @classmethod
    def from_db_model(cls, model) -> "UserEntity":
        """Создание из SQLAlchemy модели."""
        return cls(
            user_id=model.user_id,
            username=model.username,
            first_name=model.first_name,
            last_name=model.last_name,
            is_blocked=model.is_blocked,
            last_activity=model.last_activity,
            registered_at=model.registered_at,
        )
