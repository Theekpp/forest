"""SQLAlchemy database models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Float,
    Text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    """Модель пользователя Telegram."""

    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=False)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_blocked = Column(Boolean, default=False, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)
    registered_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, username={self.username})>"


class Booking(Base):
    """Модель бронирования."""

    __tablename__ = "bookings"

    booking_id = Column(String(64), primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    program = Column(String(100), nullable=False)
    date = Column(String(20), nullable=False)
    time = Column(String(20), nullable=False)
    people = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    cost = Column(Float, nullable=False)
    prepayment = Column(Float, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<Booking(booking_id={self.booking_id}, user_id={self.user_id}, status={self.status})>"


class BroadcastHistory(Base):
    """Модель истории рассылок."""

    __tablename__ = "broadcast_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    admin_id = Column(Integer, nullable=False)
    admin_username = Column(String(255), nullable=True)
    admin_name = Column(String(255), nullable=True)
    broadcast_type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    target_users = Column(String, nullable=True)  # JSON список ID пользователей
    total_sent = Column(Integer, default=0, nullable=False)
    total_failed = Column(Integer, default=0, nullable=False)
    total_blocked = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<BroadcastHistory(id={self.id}, admin_id={self.admin_id}, type={self.broadcast_type})>"
