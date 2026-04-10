from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from pydantic import model_validator
from decimal import Decimal
from pydantic import BaseModel, Field
from app.shared.enums import (
    CurrencyEnum,
    PaymentMethodEnum,
    PaymentGatewayEnum,
    PaymentStatusEnum,
    SubscriptionStatusEnum,
    languageEnum,
)


BCRYPT_MAX_PASSWORD_BYTES = 72


def _validate_password_byte_length(password: str) -> str:
    """Ensure password fits bcrypt's 72-byte UTF-8 limit."""
    password_bytes = len(password.encode("utf-8"))
    if password_bytes > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password is too long for secure hashing. Max {BCRYPT_MAX_PASSWORD_BYTES} UTF-8 bytes."
        )
    return password


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
    first_name: str = Field(
        max_length=255,
        description="User's first name",
        examples=["moustafa", "abdallah"]
    )
    last_name: str = Field(
        max_length=255,
        description="User's last name",
        examples=["magdy", "ibrahim"]
    )
    preferred_language: languageEnum = Field(
        description="User's preferred language code (e.g., 'en', 'ar')",
        examples=["ENGLISH", "ARABIC", "FRENCH"]
    )
    avatar_url: Optional[str] = Field(
        None,
        max_length=2048,
        description="URL to user's avatar image",
        examples=["https://example.com/avatars/user123.jpg"]
    )

    is_active: bool = Field(
        True,
        description="Whether the user is active",
        examples=[True]
    )

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username must contain only letters, numbers, underscores, and hyphens')
        return v.lower()

class UserCreate(UserBase):
    """Schema for creating a new user - ONLY user-provided fields, NOT database-generated ones."""
    password: str = Field(
        ...,
        min_length=8,
        max_length=100,
        description="User's password (minimum 8 characters)",
        examples=["SecurePass123!", "MyP@ssw0rd"]
    )

    is_active: bool = Field(
        True,
        description="Whether the user is active",
        examples=[True]
    )
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        _validate_password_byte_length(v)
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
        max_length=2048,
        description="Updated avatar URL",
        examples=["https://example.com/new-avatar.jpg"]
    )
    # Preferences
    default_domain: Optional[str] = Field(None, max_length=50)
    translation_style: Optional[str] = Field(None, max_length=50)
    default_voice: Optional[str] = Field(None, max_length=50)
    
    # Notifications
    notif_completed: Optional[bool] = None
    notif_credits: Optional[bool] = None
    notif_marketing: Optional[bool] = None

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
            _validate_password_byte_length(v)
            if len(v) < 8:
                raise ValueError('Password must be at least 8 characters long')
            if not any(c.isupper() for c in v):
                raise ValueError('Password must contain at least one uppercase letter')
            if not any(c.islower() for c in v):
                raise ValueError('Password must contain at least one lowercase letter')
            if not any(c.isdigit() for c in v):
                raise ValueError('Password must contain at least one digit')
        return v

    @model_validator(mode='after')
    def check_at_least_one_field(self):
        """Ensure at least one field is provided for update."""
        if not self.model_dump(exclude_unset=True):
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
    last_login: datetime = Field(
        None,
        description="Timestamp of the user's last login",
        examples=["2024-01-25T09:15:00Z"]
    )

    is_active: bool = Field(
        ...,
        description="Whether the user is active",
        examples=[True]
    )
    
    # Preferences
    default_domain: str
    translation_style: str
    default_voice: str
    
    # Notifications
    notif_completed: bool
    notif_credits: bool
    notif_marketing: bool

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
                "last_login": "2024-01-25T09:15:00Z",
                "is_active": True
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


class PasswordChangeRequest(BaseModel):
    """Schema for password change request."""
    old_password: str = Field(..., description="Current password")
    new_password: str = Field(
        ..., 
        min_length=8, 
        max_length=100, 
        description="New password (minimum 8 characters)"
    )

    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password strength."""
        _validate_password_byte_length(v)
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


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


class ForgotPasswordRequest(BaseModel):
    """Schema for forgot password request."""
    email: EmailStr = Field(
        ...,
        description="Registered user email",
        examples=["user@example.com"]
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


class SubscriptionPlanBase(BaseModel):
    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        examples=["Basic", "Pro", "Enterprise"]
    )
    description: Optional[str] = Field(
        None,
        examples=["Basic monthly plan"]
    )
    price: Decimal = Field(
        ...,
        ge=0,
        examples=["99.99", "199.00"]
    )
    is_active: bool = Field(
        True,
        examples=[True]
    )

class SubscriptionPlanCreate(SubscriptionPlanBase):
    pass


class SubscriptionPlanUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=100, description="Name of the subscription plan")
    description: Optional[str] = Field(None, description="Description of the subscription plan")
    price: Optional[float] = Field(None, ge=0, description="Price of the subscription plan")
    is_active: Optional[bool] = Field(None, description="Whether the subscription plan is active")


class SubscriptionPlanResponse(SubscriptionPlanBase):
    plan_id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserSubscriptionBase(BaseModel):
    user_id: int = Field(..., examples=[1])
    plan_id: int = Field(..., examples=[1])
    start_date: datetime = Field(
        default_factory=datetime.utcnow,
        examples=["2026-01-01T00:00:00Z"]
    )
    end_date: datetime = Field(
        ...,
        examples=["2027-01-01T00:00:00Z"]
    )

class UserSubscriptionCreate(UserSubscriptionBase):
    pass


class UserSubscriptionUpdate(BaseModel):
    plan_id: Optional[int] = Field(None, description="ID of the subscription plan")
    end_date: Optional[datetime] = Field(None, description="End date of the subscription")


class UserSubscriptionResponse(UserSubscriptionBase):
    subscription_id: int
    status: SubscriptionStatusEnum = Field(
        examples=[SubscriptionStatusEnum.ACTIVE]
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentBase(BaseModel):
    subscription_id: int = Field(..., examples=[1])
    amount: Decimal = Field(
        ...,
        ge=0,
        examples=["49.99"]
    )
    currency: CurrencyEnum = Field(
        examples=[CurrencyEnum.USD]
    )
    payment_method: PaymentMethodEnum = Field(
        examples=[PaymentMethodEnum.CARD]
    )
    payment_gateway: PaymentGatewayEnum = Field(
        examples=[PaymentGatewayEnum.STRIPE]
    )
    status: PaymentStatusEnum = Field(
        default=PaymentStatusEnum.PENDING,
        examples=[PaymentStatusEnum.PAID]
    )
    transaction_id: str = Field(
        ...,
        examples=["txn_1N9ZQe2eZvKYlo2C"]
    )

class PaymentCreate(PaymentBase):
    pass


class PaymentUpdate(BaseModel):
    amount: Optional[float] = Field(None, ge=0, description="Payment amount")
    payment_method: Optional[str] = Field(None, max_length=100, description="Payment method")
    status: Optional[str] = Field(None, max_length=50, description="Payment status")


class PaymentResponse(PaymentBase):
    payment_id: int
    payment_date: datetime

    model_config = ConfigDict(from_attributes=True)


