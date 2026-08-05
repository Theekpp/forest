"""Booking domain entity."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class BookingEntity:
    """Бизнес-объект бронирования."""

    booking_id: str
    user_id: int
    program: str
    date: str
    time: str
    people: int
    name: str
    phone: str
    cost: float
    prepayment: float
    status: str = "pending"
    timestamp: Optional[datetime] = None

    @property
    def total_due(self) -> float:
        """Сумма к доплате."""
        return self.cost - self.prepayment

    @property
    def is_paid(self) -> bool:
        """Проверка полной оплаты."""
        return self.prepayment >= self.cost

    @property
    def is_pending(self) -> bool:
        """Проверка статуса ожидания."""
        return self.status == "pending"

    @property
    def is_confirmed(self) -> bool:
        """Проверка подтверждения."""
        return self.status == "confirmed"

    @property
    def is_cancelled(self) -> bool:
        """Проверка отмены."""
        return self.status == "cancelled"

    def can_cancel(self) -> bool:
        """Можно ли отменить бронирование."""
        return self.status in ("pending", "confirmed")

    def format_details(self) -> str:
        """Форматирование деталей бронирования для отображения."""
        return f"""
📋 Бронирование #{self.booking_id[:8]}

🎯 Программа: {self.program}
📅 Дата: {self.date}
⏰ Время: {self.time}
👥 Количество человек: {self.people}
👤 Имя: {self.name}
📱 Телефон: {self.phone}

💰 Стоимость: {self.cost}₽
💳 Предоплата: {self.prepayment}₽
📊 Статус: {self.status}
"""

    @classmethod
    def from_db_model(cls, model) -> "BookingEntity":
        """Создание из SQLAlchemy модели."""
        return cls(
            booking_id=model.booking_id,
            user_id=model.user_id,
            program=model.program,
            date=model.date,
            time=model.time,
            people=model.people,
            name=model.name,
            phone=model.phone,
            cost=model.cost,
            prepayment=model.prepayment,
            status=model.status,
            timestamp=model.timestamp,
        )

    def to_dict(self) -> dict:
        """Преобразование в словарь."""
        return {
            "booking_id": self.booking_id,
            "user_id": self.user_id,
            "program": self.program,
            "date": self.date,
            "time": self.time,
            "people": self.people,
            "name": self.name,
            "phone": self.phone,
            "cost": self.cost,
            "prepayment": self.prepayment,
            "status": self.status,
        }
