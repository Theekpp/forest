"""Base repository with common CRUD operations."""

from typing import Generic, TypeVar, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """Базовый репозиторий с общими CRUD операциями."""

    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id_value: int | str) -> Optional[ModelType]:
        """Получение записи по ID."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == id_value)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[ModelType]:
        """Получение всех записей с пагинацией."""
        result = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def create(self, data: dict) -> ModelType:
        """Создание новой записи."""
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def update(self, id_value: int | str, data: dict) -> Optional[ModelType]:
        """Обновление записи."""
        stmt = (
            update(self.model)
            .where(self.model.id == id_value)  # type: ignore[attr-defined]
            .values(**data)
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return await self.get_by_id(id_value)

    async def delete(self, id_value: int | str) -> bool:
        """Удаление записи."""
        stmt = delete(self.model).where(self.model.id == id_value)  # type: ignore[attr-defined]
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0
