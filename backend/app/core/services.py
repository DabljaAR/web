from datetime import datetime
from typing import Optional, List
from fastapi import HTTPException, status
from app.core.models import User
from app.core.schema import (
    UserCreate,
    UserResponse,
    UserLoginResponse,
    UserUpdate
)
from app.core.repository import UserRepository , SubscriptionPlanRepository , UserSubscriptionRepository , PaymentRepository
from app.core.auth import AuthService
from app.core.exceptions import (
    UserAlreadyExistsException,
    InvalidCredentialsException
)


class UserService:

    def __init__(self, user_repo: UserRepository, auth_service: AuthService):
        self.user_repo = user_repo
        self.auth_service = auth_service

    async def signup(self, user_data: UserCreate) -> UserResponse:
        if await self.user_repo.username_exists(user_data.username):
            raise UserAlreadyExistsException("Username already exists")

        if await self.user_repo.email_exists(user_data.email):
            raise UserAlreadyExistsException("Email already exists")

        hashed_password = self.auth_service.get_password_hash(user_data.password)

        user_data_dict = user_data.model_dump()
        user_data_dict["password"] = hashed_password

        user = await self.user_repo.create_from_dict(user_data_dict)
        return UserResponse.model_validate(user)

    async def login(self, username: str, password: str) -> UserLoginResponse:
        user = await self.auth_service.authenticate_user(username, password)
        if not user:
            raise InvalidCredentialsException("Invalid username or password")

        await self.user_repo.update_last_login(user.user_id)

        token_pair = self.auth_service.create_token_pair(user)

        return UserLoginResponse(
            access_token=token_pair["access_token"],
            refresh_token=token_pair["refresh_token"],
            token_type=token_pair["token_type"],
            user=UserResponse.model_validate(user)
        )

    async def get_user_by_id(self, user_id: int) -> UserResponse:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return UserResponse.model_validate(user)

    async def get_all_users(self, skip: int = 0, limit: int = 10) -> List[UserResponse]:
        users = await self.user_repo.get_all(skip, limit)
        return [UserResponse.model_validate(u) for u in users]

    async def update_user(self, user_id: int, data: UserUpdate) -> UserResponse:
        if data.username and await self.user_repo.username_exists(data.username):
            raise UserAlreadyExistsException("Username already exists")

        if data.email and await self.user_repo.email_exists(data.email):
            raise UserAlreadyExistsException("Email already exists")

        update_data = data.model_dump(exclude_unset=True)

        if "password" in update_data:
            update_data["password"] = self.auth_service.get_password_hash(update_data["password"])

        user = await self.user_repo.update_from_dict(user_id, update_data)
        return UserResponse.model_validate(user)

    async def delete_user(self, user_id: int) -> bool:
        return await self.user_repo.delete(user_id)




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


