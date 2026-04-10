from datetime import datetime
from typing import TypeVar, Generic, Optional, List, Type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import DeclarativeBase
from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import inspect, func
from app.shared.enums import SubscriptionStatusEnum, PaymentStatusEnum

T = TypeVar("T", bound=DeclarativeBase)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)


class BaseRepository(Generic[T, CreateSchemaType, UpdateSchemaType]):
    
    def __init__(self, db: AsyncSession, model: Type[T]):
        self.db = db
        self.model = model
    
    async def create(self, obj_in: CreateSchemaType) -> T:
        db_obj = self.model(**obj_in.dict())
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj
    
    async def get_by_id(self, id: int) -> Optional[T]:
        pk_col = inspect(self.model).mapper.primary_key[0]
        stmt = select(self.model).where(pk_col == id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_all(self, skip: int = 0, limit: int = 10) -> List[T]:
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def update(self, id: int, obj_in: UpdateSchemaType) -> T:
        db_obj = await self.get_by_id(id)
        
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.model.__name__} not found"
            )
        
        update_data = obj_in.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj
    
    async def delete(self, id: int) -> bool:
        db_obj = await self.get_by_id(id)
        
        if not db_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.model.__name__} not found"
            )
        
        self.db.delete(db_obj)
        await self.db.commit()
        return True
    
    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        result = await self.db.execute(stmt)
        return result.scalar_one()


class UserRepository(BaseRepository):
    
    async def get_by_username(self, username: str) -> Optional[T]:
        stmt = select(self.model).where(self.model.username == username)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_email(self, email: str) -> Optional[T]:
        stmt = select(self.model).where(self.model.email == email)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_by_role(self, role_id: int, skip: int = 0, limit: int = 10) -> List[T]:
        stmt = (
            select(self.model)
            .where(self.model.role_id == role_id)
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_active_users(self, skip: int = 0, limit: int = 10) -> List[T]:
        from datetime import datetime, timedelta
        
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        stmt = (
            select(self.model)
            .where(self.model.last_login >= thirty_days_ago)
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def username_exists(self, username: str) -> bool:
        user = await self.get_by_username(username)
        return user is not None
    
    async def email_exists(self, email: str) -> bool:
        user = await self.get_by_email(email)
        return user is not None


class SubscriptionPlanRepository(BaseRepository):
    pass


class UserSubscriptionRepository(BaseRepository):
    
    async def get_by_user_id(self, user_id: int) -> List[T]:
        stmt = select(self.model).where(self.model.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_by_plan_id(self, plan_id: int) -> List[T]:
        stmt = select(self.model).where(self.model.plan_id == plan_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_active_by_user_id(self, user_id: int) -> List[T]:
        stmt = (
            select(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.status == SubscriptionStatusEnum.ACTIVE,
                self.model.end_date >= datetime.utcnow()
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()


class PaymentRepository(BaseRepository):
    
    async def get_by_subscription_id(self, subscription_id: int) -> List[T]:
        stmt = select(self.model).where(self.model.subscription_id == subscription_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_completed_by_subscription(self, subscription_id: int) -> List[T]:
        stmt = (
            select(self.model)
            .where(
                self.model.subscription_id == subscription_id,
                self.model.status == PaymentStatusEnum.PAID
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()


    async def get_by_transaction_id(self, transaction_id: str) -> Optional[T]:
        stmt = select(self.model).where(self.model.transaction_id == transaction_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

