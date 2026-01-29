import enum
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, Boolean, Float ,Numeric
from decimal import Decimal
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base
from sqlalchemy import Enum as SQLEnum
from app.core.enums import (
    CurrencyEnum,
    PaymentMethodEnum,
    PaymentGatewayEnum,
    PaymentStatusEnum,
    languageEnum,
    SubscriptionStatusEnum,
)

class Role(Base):
    __tablename__ = "roles"
    
    role_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow
    )
    
    # Note: relationship commented out as role_id doesn't exist in users table
    users: Mapped[List["User"]] = relationship("User", back_populates="role")
    
    def __repr__(self):
        return f"<Role {self.name}>"

class User(Base):
    """User model for authentication and user management."""
    __tablename__ = "users"
    
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    first_name: Mapped[str] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password: Mapped[str] = mapped_column("hashed_password", String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        default=datetime.utcnow,
    )
    preferred_language: Mapped[languageEnum] = mapped_column(SQLEnum(languageEnum, name="languages_enum"),nullable=False,default=languageEnum.ENGLISH)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, nullable=True)
    
    # Note: role_id column doesn't exist in current database schema
    role_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("roles.role_id", ondelete="SET NULL"), 
        nullable=True, 
        index=True
    )
    
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False) #online
    role: Mapped[Optional["Role"]] = relationship("Role", back_populates="users")
    subscriptions: Mapped[List["UserSubscription"]] = relationship("UserSubscription", back_populates="user")
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="user")

 
    def __repr__(self):
        return f"<User {self.username} (id={self.user_id})>"


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    plan_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate = datetime.utcnow
    )

    subscriptions: Mapped[List["UserSubscription"]] = relationship("UserSubscription", back_populates="plan")

    def __repr__(self):
        return f"<SubscriptionPlan {self.name}>"


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    subscription_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(Integer, ForeignKey("subscription_plans.plan_id"), nullable=False, index=True)
    start_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[SubscriptionStatusEnum] = mapped_column(SQLEnum(SubscriptionStatusEnum, name="subscription_status_enum"),nullable=False,default=SubscriptionStatusEnum.ACTIVE)

    user: Mapped["User"] = relationship("User", back_populates="subscriptions")
    plan: Mapped["SubscriptionPlan"] = relationship("SubscriptionPlan", back_populates="subscriptions")
    payments: Mapped[List["Payment"]] = relationship("Payment", back_populates="subscription")

    def __repr__(self):
        return f"<UserSubscription user_id={self.user_id} plan_id={self.plan_id}>"


class Payment(Base):
    __tablename__ = "payments"

    payment_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=False, index=True)
    subscription_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_subscriptions.subscription_id"),nullable=False,index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[CurrencyEnum] = mapped_column(SQLEnum(CurrencyEnum, name="currency_enum"),nullable=False,default=CurrencyEnum.USD)
    payment_method: Mapped[PaymentMethodEnum] = mapped_column(SQLEnum(PaymentMethodEnum, name="payment_method_enum"),nullable=False)
    payment_gateway: Mapped[PaymentGatewayEnum] = mapped_column(SQLEnum(PaymentGatewayEnum, name="payment_gateway_enum"),nullable=False)
    status: Mapped[PaymentStatusEnum] = mapped_column(SQLEnum(PaymentStatusEnum, name="payment_status_enum"),nullable=False,default=PaymentStatusEnum.PENDING)
    transaction_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    payment_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    subscription: Mapped["UserSubscription"] = relationship("UserSubscription", back_populates="payments")

    def __repr__(self):
        return f"<Payment user_id={self.subscription.user_id} subscription_id={self.subscription_id}>"