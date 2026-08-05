"""Broadcast history repository for database operations."""

import json
from typing import Optional, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import BroadcastHistory


class BroadcastRepository:
    """Репозиторий для операций с историей рассылок."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.model = BroadcastHistory

    async def get_by_id(self, broadcast_id: int) -> Optional[BroadcastHistory]:
        """Получение рассылки по ID."""
        result = await self.session.execute(
            select(BroadcastHistory).where(BroadcastHistory.id == broadcast_id)
        )
        return result.scalar_one_or_none()

    async def get_history(
        self, page: int = 1, per_page: int = 10
    ) -> tuple[List[BroadcastHistory], int]:
        """
        Получение истории рассылок с пагинацией.
        
        Returns:
            Кортеж (список записей, общее количество)
        """
        offset = (page - 1) * per_page
        
        # Получаем записи
        result = await self.session.execute(
            select(BroadcastHistory)
            .order_by(BroadcastHistory.created_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        broadcasts = list(result.scalars().all())
        
        # Получаем общее количество
        count_result = await self.session.execute(select(BroadcastHistory))
        total = len(list(count_result.scalars().all()))
        
        return broadcasts, total

    async def create(
        self,
        admin_id: int,
        admin_username: Optional[str],
        admin_name: Optional[str],
        broadcast_type: str,
        message: str,
        target_users: Optional[List[int]] = None,
        total_sent: int = 0,
        total_failed: int = 0,
        total_blocked: int = 0,
    ) -> BroadcastHistory:
        """Создание записи о рассылке."""
        # Преобразуем список пользователей в JSON
        target_users_json = json.dumps(target_users) if target_users else None
        
        broadcast = BroadcastHistory(
            admin_id=admin_id,
            admin_username=admin_username,
            admin_name=admin_name,
            broadcast_type=broadcast_type,
            message=message,
            target_users=target_users_json,
            total_sent=total_sent,
            total_failed=total_failed,
            total_blocked=total_blocked,
        )
        
        self.session.add(broadcast)
        await self.session.commit()
        await self.session.refresh(broadcast)
        
        return broadcast

    async def get_target_users(self, broadcast_id: int) -> Optional[List[int]]:
        """Получение списка пользователей для рассылки."""
        broadcast = await self.get_by_id(broadcast_id)
        if broadcast and broadcast.target_users:
            return json.loads(broadcast.target_users)
        return None
