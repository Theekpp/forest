"""Booking service - business logic for bookings."""

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from ..database.repositories.bookings import BookingRepository
from ..domain.entities.booking import BookingEntity
from ..core.exceptions import BookingException


class BookingService:
    """Сервис для управления бронированиями."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = BookingRepository(session)

    async def create_booking(self, data: dict) -> BookingEntity:
        """
        Создание нового бронирования.
        
        Args:
            data: Данные бронирования
            
        Returns:
            BookingEntity созданного бронирования
        """
        booking_data = {
            "booking_id": str(uuid.uuid4()),
            "user_id": data["user_id"],
            "program": data["program"],
            "date": data["date"],
            "time": data["time"],
            "people": data["people"],
            "name": data["name"],
            "phone": data["phone"],
            "cost": data["cost"],
            "prepayment": data.get("prepayment", 0),
            "status": data.get("status", "pending"),
            "timestamp": datetime.utcnow(),
        }
        
        booking = await self.repository.create(booking_data)
        return BookingEntity.from_db_model(booking)

    async def get_booking(self, booking_id: str) -> Optional[BookingEntity]:
        """Получение бронирования по ID."""
        booking = await self.repository.get_by_id(booking_id)
        if booking:
            return BookingEntity.from_db_model(booking)
        return None

    async def get_user_bookings(self, user_id: int) -> List[BookingEntity]:
        """Получение всех бронирований пользователя."""
        bookings = await self.repository.get_by_user_id(user_id)
        return [BookingEntity.from_db_model(b) for b in bookings]

    async def cancel_booking(self, booking_id: str) -> bool:
        """
        Отмена бронирования.
        
        Args:
            booking_id: ID бронирования
            
        Returns:
            True если успешно отменено
        """
        booking = await self.get_booking(booking_id)
        
        if not booking:
            raise BookingException("Бронирование не найдено", "BOOKING_NOT_FOUND")
        
        if not booking.can_cancel():
            raise BookingException(
                f"Невозможно отменить бронирование со статусом {booking.status}",
                "CANNOT_CANCEL"
            )
        
        return await self.repository.update_status(booking_id, "cancelled")

    async def confirm_booking(self, booking_id: str) -> bool:
        """Подтверждение бронирования."""
        return await self.repository.update_status(booking_id, "confirmed")

    async def update_payment_status(
        self, booking_id: str, payment_status: str
    ) -> bool:
        """Обновление статуса оплаты."""
        return await self.repository.update_payment_status(
            booking_id, payment_status
        )

    async def delete_booking(self, booking_id: str) -> bool:
        """Удаление бронирования."""
        return await self.repository.delete(booking_id)

    async def get_all_bookings(
        self, limit: int = 100, offset: int = 0
    ) -> List[BookingEntity]:
        """Получение всех бронирований с пагинацией."""
        bookings = await self.repository.get_all(limit, offset)
        return [BookingEntity.from_db_model(b) for b in bookings]
