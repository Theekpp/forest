"""Booking repository for database operations."""

from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from ..models import Booking


class BookingRepository:
    """Репозиторий для операций с бронированиями."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.model = Booking

    async def get_by_id(self, booking_id: str) -> Optional[Booking]:
        """Получение бронирования по ID."""
        result = await self.session.execute(
            select(Booking).where(Booking.booking_id == booking_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: int) -> List[Booking]:
        """Получение всех бронирований пользователя."""
        result = await self.session.execute(
            select(Booking)
            .where(Booking.user_id == user_id)
            .order_by(Booking.timestamp.desc())
        )
        return list(result.scalars().all())

    async def get_all(
        self, limit: int = 100, offset: int = 0
    ) -> List[Booking]:
        """Получение всех бронирований с пагинацией."""
        result = await self.session.execute(
            select(Booking)
            .order_by(Booking.timestamp.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> Booking:
        """Создание нового бронирования."""
        booking = Booking(**data)
        self.session.add(booking)
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    async def update_status(
        self, booking_id: str, status: str
    ) -> bool:
        """Обновление статуса бронирования."""
        stmt = (
            update(Booking)
            .where(Booking.booking_id == booking_id)
            .values(status=status)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def update_payment_status(
        self, booking_id: str, payment_status: str
    ) -> bool:
        """Обновление статуса оплаты."""
        stmt = (
            update(Booking)
            .where(Booking.booking_id == booking_id)
            .values(payment_status=payment_status)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def delete(self, booking_id: str) -> bool:
        """Удаление бронирования."""
        stmt = delete(Booking).where(Booking.booking_id == booking_id)
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def count(self) -> int:
        """Подсчет общего количества бронирований."""
        result = await self.session.execute(select(Booking))
        return len(list(result.scalars().all()))

    async def count_by_status(self, status: str) -> int:
        """Подсчет бронирований по статусу."""
        result = await self.session.execute(
            select(Booking).where(Booking.status == status)
        )
        return len(list(result.scalars().all()))

    async def get_bookings_by_date_range(
        self, start_date: str, end_date: str
    ) -> List[Booking]:
        """Получение бронирований за период."""
        result = await self.session.execute(
            select(Booking)
            .where(Booking.date >= start_date)
            .where(Booking.date <= end_date)
            .order_by(Booking.date)
        )
        return list(result.scalars().all())
