from datetime import datetime
from typing import Optional, List
from sqlalchemy import Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base

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
    first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
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
        onupdate=datetime.utcnow
    )
    preferred_language: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, default=True, nullable=True)
    
    # Note: role_id column doesn't exist in current database schema
    role_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        ForeignKey("roles.role_id", ondelete="SET NULL"), 
        nullable=True, 
        index=True
    )
    
    role: Mapped[Optional["Role"]] = relationship("Role", back_populates="users")
 
    def __repr__(self):
        return f"<User {self.username} (id={self.user_id})>"