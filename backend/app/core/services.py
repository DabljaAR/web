from datetime import datetime
from sqlalchemy import true
from typing import Optional, List
from fastapi import HTTPException, status
from app.core.models import User
from app.core.schema import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserLoginResponse,
    SubscriptionPlanCreate,
    SubscriptionPlanUpdate,
    SubscriptionPlanResponse,
    UserSubscriptionCreate,
    UserSubscriptionUpdate,
    UserSubscriptionResponse,
    PaymentCreate,
    PaymentUpdate,
    PaymentResponse
)
from app.core.repository import UserRepository, SubscriptionPlanRepository, UserSubscriptionRepository, PaymentRepository
from app.core.auth import AuthService
from app.core.exceptions import (
    UserAlreadyExistsException,
    InvalidCredentialsException
)
from app.config import settings
import logging
logger = logging.getLogger(__name__)
class UserService:
    """User service with dependency injection."""
    
    def __init__(self, user_repo: UserRepository, auth_service: AuthService):
        """
        Initialize UserService with repository and auth service dependencies.
        
        Args:
            user_repo: UserRepository instance for data access
            auth_service: AuthService instance for authentication
        """
        self.user_repo = user_repo
        self.auth_service = auth_service
    
    async def signup(self, user_data: UserCreate) -> UserResponse:
        """
        Register a new user.
        
        Args:
            user_data: User creation data
            
        Returns:
            UserResponse with created user data
            
        Raises:
            UserAlreadyExistsException: If username or email already exists
        """
        # Check if username already exists
        if await self.user_repo.username_exists(user_data.username):
            raise UserAlreadyExistsException(
                f"Username '{user_data.username}' is already registered"
            )
        
        # Check if email already exists
        if await self.user_repo.email_exists(user_data.email):
            raise UserAlreadyExistsException(
                f"Email '{user_data.email}' is already registered"
            )
        
        # Hash password
        hashed_password = self.auth_service.get_password_hash(user_data.password)
        
        # Create user model
        db_user = User(
            username=user_data.username,
            email=user_data.email,
            password=hashed_password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            preferred_language=user_data.preferred_language,
            avatar_url=user_data.avatar_url,
            is_active = user_data.is_active
        )
        
        # Save to database
        self.user_repo.db.add(db_user)
        await self.user_repo.db.commit()
        await self.user_repo.db.refresh(db_user)
        
        logger.info(db_user)
        # Return user response
        return UserResponse.model_validate(db_user)
    
    async def login(self, username: str, password: str) -> UserLoginResponse:
        """
        Authenticate user and generate tokens.
        
        Args:
            username: Username or email
            password: Plain text password
            
        Returns:
            UserLoginResponse with tokens and user data
            
        Raises:
            InvalidCredentialsException: If credentials are invalid
        """
        # Authenticate user
        user = await self.auth_service.authenticate_user(username, password)
        
        if not user:
            raise InvalidCredentialsException("Invalid username or password")
        
        # Update last login timestamp
        user.last_login = datetime.utcnow()
        self.user_repo.db.add(user)
        await self.user_repo.db.commit()
        
        # Generate token pair
        token_pair = self.auth_service.create_token_pair(user)
        
        # Build response
        user_response = UserResponse.model_validate(user)
        
        return UserLoginResponse(
            access_token=token_pair["access_token"],
            refresh_token=token_pair["refresh_token"],
            token_type=token_pair["token_type"],
            user=user_response
        )
    
    async def refresh_token(self, refresh_token: str) -> dict:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            Dictionary with new access_token and refresh_token
            
        Raises:
            InvalidCredentialsException: If refresh token is invalid
            TokenExpiredException: If refresh token has expired
        """
        return await self.auth_service.refresh_access_token(refresh_token)
    
    async def get_user_by_id(self, user_id: int) -> UserResponse:
        """
        Get a user by ID.
        
        Args:
            user_id: User ID to retrieve
            
        Returns:
            UserResponse with user data
            
        Raises:
            HTTPException: If user not found (404)
        """
        user = await self.user_repo.get_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        return UserResponse.model_validate(user)
    
    async def get_all_users(self, skip: int = 0, limit: int = 10) -> List[UserResponse]:
        """
        Get all users with pagination.
        
        Args:
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            
        Returns:
            List of UserResponse objects
        """
        users = await self.user_repo.get_all(skip=skip, limit=limit)
        return [UserResponse.model_validate(user) for user in users]
    
    async def update_user(self, user_id: int, user_data: UserUpdate) -> UserResponse:
        """
        Update a user's information.
        
        Args:
            user_id: User ID to update
            user_data: User update data (partial)
            
        Returns:
            UserResponse with updated user data
            
        Raises:
            HTTPException: If user not found (404)
            UserAlreadyExistsException: If username or email already exists
        """
        # Get existing user
        user = await self.user_repo.get_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        # Check if username is being updated and already exists
        if user_data.username and user_data.username != user.username:
            if await self.user_repo.username_exists(user_data.username):
                raise UserAlreadyExistsException(
                    f"Username '{user_data.username}' is already registered"
                )
        
        # Check if email is being updated and already exists
        if user_data.email and user_data.email != user.email:
            if await self.user_repo.email_exists(user_data.email):
                raise UserAlreadyExistsException(
                    f"Email '{user_data.email}' is already registered"
                )
        
        # Prepare update data
        update_data = user_data.model_dump(exclude_unset=True, exclude={'password'})
        
        # Hash password if provided
        if user_data.password:
            update_data['password'] = self.auth_service.get_password_hash(user_data.password)
        
        # Update user fields
        for field, value in update_data.items():
            setattr(user, field, value)
        
        # Update timestamp
        user.updated_at = datetime.utcnow()
        
        # Save changes
        self.user_repo.db.add(user)
        await self.user_repo.db.commit()
        await self.user_repo.db.refresh(user)
        
        return UserResponse.model_validate(user)
    
    async def delete_user(self, user_id: int) -> bool:
        """
        Delete a user by ID.
        
        Args:
            user_id: User ID to delete
            
        Returns:
            True if deletion successful
            
        Raises:
            HTTPException: If user not found (404)
        """
        user = await self.user_repo.get_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with ID {user_id} not found"
            )
        
        await self.user_repo.db.delete(user)
        await self.user_repo.db.commit()
        
        return True

class SubscriptionPlanService:
    def __init__(self, subscription_plan_repo: "SubscriptionPlanRepository"):
        self.subscription_plan_repo = subscription_plan_repo

    async def create_plan(self, plan_data: "SubscriptionPlanCreate") -> "SubscriptionPlanResponse":
        plan = await self.subscription_plan_repo.create(plan_data)
        return SubscriptionPlanResponse.model_validate(plan)

    async def get_plan_by_id(self, plan_id: int) -> "SubscriptionPlanResponse":
        plan = await self.subscription_plan_repo.get_by_id(plan_id)
        if not plan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription plan not found")
        return SubscriptionPlanResponse.model_validate(plan)

    async def get_all_plans(self, skip: int = 0, limit: int = 10) -> List["SubscriptionPlanResponse"]:
        plans = await self.subscription_plan_repo.get_all(skip=skip, limit=limit)
        return [SubscriptionPlanResponse.model_validate(plan) for plan in plans]

    async def update_plan(self, plan_id: int, plan_data: "SubscriptionPlanUpdate") -> "SubscriptionPlanResponse":
        plan = await self.subscription_plan_repo.update(plan_id, plan_data)
        return SubscriptionPlanResponse.model_validate(plan)

    async def delete_plan(self, plan_id: int) -> bool:
        return await self.subscription_plan_repo.delete(plan_id)


class UserSubscriptionService:
    def __init__(self, user_subscription_repo: "UserSubscriptionRepository"):
        self.user_subscription_repo = user_subscription_repo

    async def create_subscription(self, subscription_data: "UserSubscriptionCreate") -> "UserSubscriptionResponse":
        subscription = await self.user_subscription_repo.create(subscription_data)
        return UserSubscriptionResponse.model_validate(subscription)

    async def get_subscription_by_id(self, subscription_id: int) -> "UserSubscriptionResponse":
        subscription = await self.user_subscription_repo.get_by_id(subscription_id)
        if not subscription:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User subscription not found")
        return UserSubscriptionResponse.model_validate(subscription)

    async def get_all_subscriptions(self, skip: int = 0, limit: int = 10) -> List["UserSubscriptionResponse"]:
        subscriptions = await self.user_subscription_repo.get_all(skip=skip, limit=limit)
        return [UserSubscriptionResponse.model_validate(sub) for sub in subscriptions]

    async def update_subscription(self, subscription_id: int, subscription_data: "UserSubscriptionUpdate") -> "UserSubscriptionResponse":
        subscription = await self.user_subscription_repo.update(subscription_id, subscription_data)
        return UserSubscriptionResponse.model_validate(subscription)

    async def delete_subscription(self, subscription_id: int) -> bool:
        return await self.user_subscription_repo.delete(subscription_id)


class PaymentService:
    def __init__(self, payment_repo: "PaymentRepository"):
        self.payment_repo = payment_repo

    async def create_payment(self, payment_data: "PaymentCreate") -> "PaymentResponse":
        payment = await self.payment_repo.create(payment_data)
        return PaymentResponse.model_validate(payment)

    async def get_payment_by_id(self, payment_id: int) -> "PaymentResponse":
        payment = await self.payment_repo.get_by_id(payment_id)
        if not payment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
        return PaymentResponse.model_validate(payment)

    async def get_all_payments(self, skip: int = 0, limit: int = 10) -> List["PaymentResponse"]:
        payments = await self.payment_repo.get_all(skip=skip, limit=limit)
        return [PaymentResponse.model_validate(payment) for payment in payments]

    async def update_payment(self, payment_id: int, payment_data: "PaymentUpdate") -> "PaymentResponse":
        payment = await self.payment_repo.update(payment_id, payment_data)
        return PaymentResponse.model_validate(payment)

    async def delete_payment(self, payment_id: int) -> bool:
        return await self.payment_repo.delete(payment_id)