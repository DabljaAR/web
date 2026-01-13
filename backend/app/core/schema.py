from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from pydantic import model_validator



class UserBase(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Unique username for the user",
        examples=["moustafa", "abdallah"]
    )
    email: EmailStr = Field(
        ...,
        description="User's email address",
        examples=["user@example.com", "moustafa@company.com"]
    )
    first_name: Optional[str] = Field(
        None,
        max_length=255,
        description="User's first name",
        examples=["moustafa", "abdallah"]
    )
    last_name: Optional[str] = Field(
        None,
        max_length=255,
        description="User's last name",
        examples=["magdy", "ibrahim"]
    )
    preferred_language: Optional[str] = Field(
        None,
        max_length=10,
        description="User's preferred language code (e.g., 'en', 'ar')",
        examples=["en", "ar", "fr"]
    )
    avatar_url: Optional[str] = Field(
        None,
        max_length=500,
        description="URL to user's avatar image",
        examples=["https://example.com/avatars/user123.jpg"]
    )

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username must contain only letters, numbers, underscores, and hyphens')
        return v.lower()

    @field_validator('preferred_language')
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        
        if v is not None and len(v) > 10:
            raise ValueError('Language code must be 10 characters or less')
        return v.lower() if v else v


class UserCreate(UserBase):
    """Schema for creating a new user."""
    password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="User's password (minimum 8 characters)",
        examples=["SecurePass123!", "MyP@ssw0rd"]
    )

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "moustafa",
                "email": "moustafa@example.com",
                "password": "SecurePass123!",
                "first_name": "moustafa",
                "last_name": "magdy",
                "preferred_language": "en",
                "avatar_url": None
            }
        }
    )


# ============================================================================
# Update Schema - Fields that can be modified (all optional)
# ============================================================================

class UserUpdate(BaseModel):
    """Schema for updating user information."""
    username: Optional[str] = Field(
        None,
        min_length=3,
        max_length=50,
        description="Updated username",
        examples=["new_username"]
    )
    email: Optional[EmailStr] = Field(
        None,
        description="Updated email address",
        examples=["newemail@example.com"]
    )
    first_name: Optional[str] = Field(
        None,
        max_length=255,
        description="Updated first name",
        examples=["moustafa"]
    )
    last_name: Optional[str] = Field(
        None,
        max_length=255,
        description="Updated last name",
        examples=["magdy"]
    )
    password: Optional[str] = Field(
        None,
        min_length=8,
        max_length=100,
        description="New password (minimum 8 characters)",
        examples=["NewSecurePass123!"]
    )
    preferred_language: Optional[str] = Field(
        None,
        max_length=10,
        description="Updated preferred language",
        examples=["ar"]
    )
    avatar_url: Optional[str] = Field(
        None,
        max_length=500,
        description="Updated avatar URL",
        examples=["https://example.com/new-avatar.jpg"]
    )

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        """Validate username format if provided."""
        if v is not None:
            if not v.replace('_', '').replace('-', '').isalnum():
                raise ValueError('Username must contain only letters, numbers, underscores, and hyphens')
            return v.lower()
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """Validate password strength if provided."""
        if v is not None:
            if len(v) < 8:
                raise ValueError('Password must be at least 8 characters long')
            if not any(c.isupper() for c in v):
                raise ValueError('Password must contain at least one uppercase letter')
            if not any(c.islower() for c in v):
                raise ValueError('Password must contain at least one lowercase letter')
            if not any(c.isdigit() for c in v):
                raise ValueError('Password must contain at least one digit')
        return v

    @field_validator('preferred_language')
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        """Validate language code format if provided."""
        if v is not None and len(v) > 10:
            raise ValueError('Language code must be 10 characters or less')
        return v.lower() if v else v

    @model_validator(mode='after')
    def check_at_least_one_field(self):
        """Ensure at least one field is provided for update."""
        if all(value is None for value in self.model_dump().values()):
            raise ValueError('At least one field must be provided for update')
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "first_name": "John",
                "last_name": "Doe",
                "preferred_language": "ar",
                "avatar_url": "https://example.com/avatar.jpg"
            }
        }
    )


# ============================================================================
# Response Schema - Complete entity representation for API responses
# ============================================================================

class UserResponse(UserBase):
    user_id: int = Field(
        ...,
        description="Unique identifier for the user",
        examples=[1, 100]
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when the user was created",
        examples=["2024-01-15T10:30:00Z"]
    )
    updated_at: datetime = Field(
        ...,
        description="Timestamp when the user was last updated",
        examples=["2024-01-20T14:45:00Z"]
    )
    last_login: Optional[datetime] = Field(
        None,
        description="Timestamp of the user's last login",
        examples=["2024-01-25T09:15:00Z"]
    )

    model_config = ConfigDict(
        from_attributes=True,  # Allows conversion from SQLAlchemy models
        json_schema_extra={
            "example": {
                "user_id": 1,
                "username": "johndoe",
                "email": "john.doe@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "preferred_language": "en",
                "avatar_url": "https://example.com/avatars/user123.jpg",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-20T14:45:00Z",
                "last_login": "2024-01-25T09:15:00Z"
            }
        }
    )


# ============================================================================
# Additional Response Schemas
# ============================================================================

class UserPublicResponse(BaseModel):
    """Public user response (without sensitive information)."""
    user_id: int
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    preferred_language: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    """Schema for user login request."""
    username: str = Field(
        ...,
        description="Username or email for login",
        examples=["moustafa", "user@example.com"]
    )
    password: str = Field(
        ...,
        description="User password",
        examples=["SecurePass123!"]
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "username": "moustafa",
                "password": "SecurePass123!"
            }
        }
    )


class TokenRefresh(BaseModel):
    """Schema for refresh token request."""
    refresh_token: str = Field(
        ...,
        description="Refresh token to get a new access token",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."]
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }
    )


class TokenResponse(BaseModel):
    """Response schema for token generation (login/refresh)."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer"
            }
        }
    )


class UserLoginResponse(BaseModel):
    """Response schema for user login with user information."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    user: UserResponse = Field(..., description="User information")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "user_id": 1,
                    "username": "moustafa",
                    "email": "moustafa@example.com",
                    "first_name": "moustafa",
                    "last_name": "magdy"
                }
            }
        }
    )
