"""User repository for database operations."""

from typing import Optional, List
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..models import User


class UserRepository:
    """Репозиторий для операций с пользователями."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.model = User

    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Получение пользователя по ID."""
        result = await self.session.execute(
            select(User).where(User.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self, limit: int = 100, offset: int = 0
    ) -> List[User]:
        """Получение всех пользователей с пагинацией."""
        result = await self.session.execute(
            select(User)
            .order_by(User.registered_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_active_users(
        self, limit: int = 100, offset: int = 0
    ) -> List[User]:
        """Получение активных (не заблокированных) пользователей."""
        result = await self.session.execute(
            select(User)
            .where(User.is_blocked == False)
            .order_by(User.last_activity.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def create_or_update(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """Создание или обновление пользователя."""
        now = datetime.utcnow()
        
        # Проверяем существующего пользователя
        existing = await self.get_by_id(user_id)
        
        if existing:
            # Обновляем данные
            stmt = (
                update(User)
                .where(User.user_id == user_id)
                .values(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    last_activity=now,
                )
            )
            await self.session.execute(stmt)
            await self.session.commit()
            return await self.get_by_id(user_id)  # type: ignore[return-value]
        else:
            # Создаем нового
            user = User(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                last_activity=now,
                registered_at=now,
                is_blocked=False,
            )
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
            return user

    async def block_user(self, user_id: int) -> bool:
        """Блокировка пользователя."""
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(is_blocked=True)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def unblock_user(self, user_id: int) -> bool:
        """Разблокировка пользователя."""
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(is_blocked=False)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def count(self) -> int:
        """Подсчет общего количества пользователей."""
        result = await self.session.execute(select(User))
        return len(list(result.scalars().all()))

    async def count_active(self) -> int:
        """Подсчет активных пользователей."""
        result = await self.session.execute(
            select(User).where(User.is_blocked == False)
        )
        return len(list(result.scalars().all()))
