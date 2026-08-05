"""Broadcast domain entity."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


@dataclass
class BroadcastEntity:
    """Бизнес-объект рассылки."""

    id: Optional[int] = None
    admin_id: int = 0
    admin_username: Optional[str] = None
    admin_name: Optional[str] = None
    broadcast_type: str = "all"  # "all" или "selected"
    message: str = ""
    target_users: Optional[List[int]] = None
    total_sent: int = 0
    total_failed: int = 0
    total_blocked: int = 0
    created_at: Optional[datetime] = None

    @property
    def total_recipients(self) -> int:
        """Общее количество получателей."""
        return self.total_sent + self.total_failed + self.total_blocked

    @property
    def success_rate(self) -> float:
        """Процент успешной доставки."""
        if self.total_recipients == 0:
            return 0.0
        return (self.total_sent / self.total_recipients) * 100

    def is_targeted(self) -> bool:
        """Является ли рассылка целевой (не всем)."""
        return self.broadcast_type == "selected" and bool(self.target_users)

    def format_summary(self) -> str:
        """Форматирование сводки о рассылке."""
        status_emoji = "✅" if self.total_failed == 0 else "⚠️"
        return f"""
{status_emoji} Рассылка #{self.id}

👤 Администратор: {self.admin_name or self.admin_username}
📋 Тип: {'Выборочная' if self.is_targeted() else 'Общая'}
📨 Отправлено: {self.total_sent}
❌ Не доставлено: {self.total_failed}
🚫 Заблокировано: {self.total_blocked}
📊 Успешность: {self.success_rate:.1f}%
"""

    @classmethod
    def from_db_model(cls, model) -> "BroadcastEntity":
        """Создание из SQLAlchemy модели."""
        import json
        
        target_users = None
        if model.target_users:
            try:
                target_users = json.loads(model.target_users)
            except (json.JSONDecodeError, TypeError):
                target_users = None
        
        return cls(
            id=model.id,
            admin_id=model.admin_id,
            admin_username=model.admin_username,
            admin_name=model.admin_name,
            broadcast_type=model.broadcast_type,
            message=model.message,
            target_users=target_users,
            total_sent=model.total_sent,
            total_failed=model.total_failed,
            total_blocked=model.total_blocked,
            created_at=model.created_at,
        )
