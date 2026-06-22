from datetime import datetime, timezone
from typing import List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
import logging
from app.storage import get_storage_service, StorageService
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schema import (
    UserCreate, UserLogin, TokenRefresh, UserLoginResponse, TokenResponse, 
    UserResponse, UserUpdate, PasswordChangeRequest, SubscriptionPlanCreate, SubscriptionPlanResponse,
    SubscriptionPlanUpdate, UserSubscriptionCreate, UserSubscriptionResponse, ForgotPasswordRequest,
    UserSubscriptionUpdate, PaymentCreate, PaymentResponse, PaymentUpdate
)
from app.core.db import get_db
from app.core.models import User, SubscriptionPlan, UserSubscription, Payment
from app.core.repository import (
    UserRepository, SubscriptionPlanRepository, 
    UserSubscriptionRepository, PaymentRepository
)
from app.core.auth import AuthService, PasswordValidationError, get_auth_service, get_current_user
from app.core.services import UserService, SubscriptionPlanService, UserSubscriptionService, PaymentService
from app.core.exceptions import UserAlreadyExistsException, InvalidCredentialsException, TokenExpiredException
from app.core.rate_limiter import limiter
from fastapi import Request


router = APIRouter()
logger = logging.getLogger(__name__)

# Allowed image extensions
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB



def get_user_service(
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
    storage_service: StorageService = Depends(get_storage_service)
) -> UserService:
    """
    Dependency injection factory for UserService.
    
    Args:
        db: Database session (injected)
        auth_service: AuthService instance (injected)
        storage_service: StorageService instance (injected)
        
    Returns:
        UserService instance with injected dependencies
    """
    user_repo = UserRepository(db, User)
    return UserService(user_repo, auth_service, storage_service)

def get_subscription_plan_service(
    db: AsyncSession = Depends(get_db)
) -> SubscriptionPlanService:
    """Dependency injection factory for SubscriptionPlanService."""
    repo = SubscriptionPlanRepository(db, SubscriptionPlan)
    return SubscriptionPlanService(repo)


def get_user_subscription_service(
    db: AsyncSession = Depends(get_db)
) -> UserSubscriptionService:
    """Dependency injection factory for UserSubscriptionService."""
    repo = UserSubscriptionRepository(db, UserSubscription)
    return UserSubscriptionService(repo)


def get_payment_service(
    db: AsyncSession = Depends(get_db)
) -> PaymentService:
    """Dependency injection factory for PaymentService."""
    repo = PaymentRepository(db, Payment)
    return PaymentService(repo)


@router.post("/signup", response_model=UserLoginResponse, status_code=status.HTTP_201_CREATED, tags=["auth"])
@limiter.limit("5/minute")
async def signup(
    request: Request,
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service)
):
    """
    Register a new user and return tokens.
    
    - **username**: Unique username (3-50 characters)
    - **email**: Valid email address
    - **password**: Password (min 8 chars, must contain uppercase, lowercase, and digit)
    - **first_name**: Optional first name
    - **last_name**: Optional last name
    - **preferred_language**: Optional language code
    - **avatar_url**: Optional avatar URL
    
    Returns created user data and access tokens.
    """
    try:
        return await user_service.signup(user_data)
    except UserAlreadyExistsException as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e.detail)
        )
    except PasswordValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Signup error", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/login", response_model=UserLoginResponse, tags=["auth"])
@limiter.limit("5/minute")
async def login(
    request: Request,
    login_data: UserLogin,
    user_service: UserService = Depends(get_user_service)
):
    """
    Authenticate user and get access/refresh tokens.
    
    - **username**: Username or email
    - **password**: User password
    
    Returns access token, refresh token, and user information.
    """
    # Test logging 
    # import logging
    # import traceback
    # logger = logging.getLogger(__name__)
    # logger.error("Test error", exc_info=True)
    # logger.warning("Test warning", exc_info=True)
    # logger.info("Test info", exc_info=True)
    # logger.debug("Test debug", exc_info=True)
    # logger.error("Test error", exc_info=True)
    # logger.critical("Test critical", exc_info=True)
    # raise Exception("Test error")
    try:
        return await user_service.login(login_data.username, login_data.password)
    except InvalidCredentialsException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e.detail),
            headers={"WWW-Authenticate": "Bearer"}
        )


@router.post("/auth/refresh", response_model=TokenResponse, tags=["auth"])
async def refresh_token(
    token_data: TokenRefresh,
    user_service: UserService = Depends(get_user_service)
):
    """
    Refresh access token using refresh token.
    
    - **refresh_token**: Valid refresh token
    
    Returns new access token and refresh token (token rotation).
    """
    try:
        tokens = await user_service.refresh_token(token_data.refresh_token)
        return TokenResponse(**tokens)
    except (InvalidCredentialsException, TokenExpiredException) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e.detail),
            headers={"WWW-Authenticate": "Bearer"}
        )


@router.get("/auth/me", response_model=UserResponse, tags=["auth"])
async def auth_me(current_user: User = Depends(get_current_user)):
    """Get the current authenticated user."""
    return UserResponse.model_validate(current_user)


@router.post("/auth/logout", tags=["auth"])
async def logout(current_user: User = Depends(get_current_user)):
    """Logout endpoint placeholder for token-based clients."""
    return {"message": "Logged out successfully"}


@router.post("/auth/forgot-password", tags=["auth"])
async def forgot_password(payload: ForgotPasswordRequest):
    """Placeholder forgot-password endpoint to keep API contract consistent."""
    return {
        "message": "If the email exists, a password reset link has been sent.",
        "email": payload.email,
    }


@router.get("/users/{user_id}", response_model=UserResponse, tags=["users"])
async def get_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
):
    """
    Get a user by ID.
    
    - **user_id**: User ID to retrieve
    
    Requires JWT authentication.
    Returns user data.
    """
    return await user_service.get_user_by_id(user_id)


@router.get("/users", response_model=List[UserResponse], tags=["users"])
async def get_all_users(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of records to return"),
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
):
    """
    Get all users with pagination.
    
    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return (1-100)
    
    Requires JWT authentication.
    Returns list of users.
    """
    return await user_service.get_all_users(skip=skip, limit=limit)


@router.put("/users/{user_id}", response_model=UserResponse, tags=["users"])
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
):
    """
    Update a user's information.
    
    - **user_id**: User ID to update
    - **user_data**: User update data (all fields optional)
    
    Requires JWT authentication.
    Returns updated user data.
    """
    try:
        return await user_service.update_user(user_id, user_data)
    except UserAlreadyExistsException as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e.detail)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@router.post("/users/{user_id}/change-password", tags=["users"])
async def change_password(
    user_id: int,
    password_data: PasswordChangeRequest,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
):
    """
    Change a user's password.
    
    - **user_id**: User ID to update
    - **password_data**: Old and new password
    
    Requires JWT authentication.
    """
    # Permission check: users can only change their own password
    if current_user.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only change your own password"
        )
        
    try:
        return await user_service.change_password(user_id, password_data.old_password, password_data.new_password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["users"])
async def delete_user(
    user_id: int,
    user_service: UserService = Depends(get_user_service),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a user by ID.
    
    - **user_id**: User ID to delete
    
    Requires JWT authentication.
    Returns 204 No Content on success.
    """
    await user_service.delete_user(user_id)
    return None


# @router.post("/upload/avatar", tags=["upload"], dependencies=[Depends(get_current_user)])
@router.post("/upload/avatar", tags=["upload"])
async def upload_avatar(
    file: UploadFile = File(...),
    storage: StorageService = Depends(get_storage_service)
):
    """
    Upload an avatar image.
    
    - **file**: Image file (jpg, jpeg, png, gif, webp, max 5MB)
    
    Returns the URL of the uploaded file.
    """
    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Read file content to check size
    contents = await file.read()
    file_size = len(contents)
    await file.seek(0)  # Reset file pointer for storage service
    
    # Validate file size
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    try:
        # Save file using storage service
        file_key = await storage.save(file, directory="avatars")
        
        # Get URL for the uploaded file
        file_url = await storage.get_url(file_key)
        
        return {"url": file_url, "filename": Path(file_key).name}
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error uploading avatar: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error uploading file to storage server"
        )


@router.get("/health", tags=["health"])
async def health_check():
    """
    Simple health check endpoint.
    Returns service status and current UTC timestamp.
    """
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat() + "Z"}





# subscription_plans_router = APIRouter(prefix="/subscription-plans", tags=["subscription-plans"])


@router.post("/subscription-plans", response_model=SubscriptionPlanResponse, status_code=status.HTTP_201_CREATED, tags=["subscription-plans"])
async def create_subscription_plan(
    data: SubscriptionPlanCreate,
    service: SubscriptionPlanService = Depends(get_subscription_plan_service),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new subscription plan.
    
    Request body:
    - **name**: Plan name (3-100 characters)
    - **description**: Plan description
    - **price**: Plan price (>= 0)
    - **is_active**: Whether the plan is active
    
    Requires JWT authentication.
    
    Returns:
        Created subscription plan
    """
    return await service.create_plan(data)


@router.get("/subscription-plans", response_model=List[SubscriptionPlanResponse], tags=["subscription-plans"])
async def list_subscription_plans(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    service: SubscriptionPlanService = Depends(get_subscription_plan_service),
    current_user: User = Depends(get_current_user)
):
    """
    Get all subscription plans with pagination.
    
    Query parameters:
    - **skip**: Number of records to skip
    - **limit**: Maximum number of records to return
    
    Requires JWT authentication.
    
    Returns:
        List of subscription plans
    """
    return await service.get_all_plans(skip=skip, limit=limit)


@router.get("/subscription-plans/{plan_id}", response_model=SubscriptionPlanResponse, tags=["subscription-plans"])
async def get_subscription_plan(
    plan_id: int,
    service: SubscriptionPlanService = Depends(get_subscription_plan_service),
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific subscription plan by ID.
    
    Path parameters:
    - **plan_id**: Subscription plan ID
    
    Requires JWT authentication.
    
    Returns:
        Subscription plan data
        
    Raises:
        404 Not Found: Plan not found
    """
    return await service.get_plan_by_id(plan_id)


@router.put("/subscription-plans/{plan_id}", response_model=SubscriptionPlanResponse, tags=["subscription-plans"])
async def update_subscription_plan(
    plan_id: int,
    data: SubscriptionPlanUpdate,
    service: SubscriptionPlanService = Depends(get_subscription_plan_service),
    current_user: User = Depends(get_current_user)
):
    """
    Update a subscription plan.
    
    Path parameters:
    - **plan_id**: Subscription plan ID
    
    Request body:
    - **data**: Plan update data (all fields optional)
    
    Requires JWT authentication.
    
    Returns:
        Updated subscription plan
        
    Raises:
        404 Not Found: Plan not found
    """
    return await service.update_plan(plan_id, data)


@router.delete("/subscription-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["subscription-plans"])
async def delete_subscription_plan(
    plan_id: int,
    service: SubscriptionPlanService = Depends(get_subscription_plan_service),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a subscription plan.
    
    Path parameters:
    - **plan_id**: Subscription plan ID
    
    Requires JWT authentication.
    
    Returns:
        204 No Content on success
        
    Raises:
        404 Not Found: Plan not found
    """
    await service.delete_plan(plan_id)
    return None


# ============================================================================
# User Subscription Routes
# ============================================================================


@router.post("/subscriptions", response_model=UserSubscriptionResponse, status_code=status.HTTP_201_CREATED, tags=["subscriptions"])
async def subscribe(
    data: UserSubscriptionCreate,
    service: UserSubscriptionService = Depends(get_user_subscription_service),
    current_user: User = Depends(get_current_user)
):
    """
    Subscribe user to a subscription plan.
    
    Request body:
    - **user_id**: User ID
    - **plan_id**: Subscription plan ID
    - **start_date**: Subscription start date
    - **end_date**: Subscription end date
    
    Requires JWT authentication.
    
    Returns:
        Created user subscription
    """
    return await service.create_subscription(data)


@router.get("/subscriptions", response_model=List[UserSubscriptionResponse], tags=["subscriptions"])
async def list_subscriptions(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    service: UserSubscriptionService = Depends(get_user_subscription_service),
    current_user: User = Depends(get_current_user)
):
    """
    Get all user subscriptions with pagination.
    
    Query parameters:
    - **skip**: Number of records to skip
    - **limit**: Maximum number of records to return
    
    Requires JWT authentication.
    
    Returns:
        List of user subscriptions
    """
    return await service.get_all_subscriptions(skip=skip, limit=limit)


@router.get("/subscriptions/me", response_model=List[UserSubscriptionResponse], tags=["subscriptions"])
async def my_subscriptions(
    service: UserSubscriptionService = Depends(get_user_subscription_service),
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's subscriptions.
    
    Requires JWT authentication.
    
    Returns:
        List of current user's subscriptions
    """
    return await service.get_user_subscriptions(current_user.user_id)


@router.get("/subscriptions/{subscription_id}", response_model=UserSubscriptionResponse, tags=["subscriptions"])
async def get_subscription(
    subscription_id: int,
    service: UserSubscriptionService = Depends(get_user_subscription_service),
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific user subscription by ID.
    
    Path parameters:
    - **subscription_id**: User subscription ID
    
    Requires JWT authentication.
    
    Returns:
        User subscription data
        
    Raises:
        404 Not Found: Subscription not found
    """
    return await service.get_subscription_by_id(subscription_id)


@router.put("/subscriptions/{subscription_id}", response_model=UserSubscriptionResponse, tags=["subscriptions"])
async def update_subscription(
    subscription_id: int,
    data: UserSubscriptionUpdate,
    service: UserSubscriptionService = Depends(get_user_subscription_service),
    current_user: User = Depends(get_current_user)
):
    """
    Update a user subscription.
    
    Path parameters:
    - **subscription_id**: User subscription ID
    
    Request body:
    - **data**: Subscription update data (all fields optional)
    
    Requires JWT authentication.
    
    Returns:
        Updated user subscription
        
    Raises:
        404 Not Found: Subscription not found
    """
    return await service.update_subscription(subscription_id, data)


@router.delete("/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["subscriptions"])
async def delete_subscription(
    subscription_id: int,
    service: UserSubscriptionService = Depends(get_user_subscription_service),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a user subscription.
    
    Path parameters:
    - **subscription_id**: User subscription ID
    
    Requires JWT authentication.
    
    Returns:
        204 No Content on success
        
    Raises:
        404 Not Found: Subscription not found
    """
    await service.delete_subscription(subscription_id)
    return None


# ============================================================================
# Payment Routes
# ============================================================================


@router.post("/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED, tags=["payments"])
async def create_payment(
    data: PaymentCreate,
    service: PaymentService = Depends(get_payment_service),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new payment.
    
    Request body:
    - **subscription_id**: User subscription ID
    - **amount**: Payment amount
    - **currency**: Currency (e.g., USD)
    - **payment_method**: Payment method (e.g., CARD)
    - **payment_gateway**: Payment gateway (e.g., STRIPE)
    - **status**: Payment status
    - **transaction_id**: Transaction ID from payment gateway
    
    Requires JWT authentication.
    
    Returns:
        Created payment
    """
    return await service.create_payment(data)


@router.get("/payments", response_model=List[PaymentResponse], tags=["payments"])
async def list_payments(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    service: PaymentService = Depends(get_payment_service),
    current_user: User = Depends(get_current_user)
):
    """
    Get all payments with pagination.
    
    Query parameters:
    - **skip**: Number of records to skip
    - **limit**: Maximum number of records to return
    
    Requires JWT authentication.
    
    Returns:
        List of payments
    """
    return await service.get_all_payments(skip=skip, limit=limit)


@router.get("/payments/me", response_model=List[PaymentResponse], tags=["payments"])
async def my_payments(
    service: PaymentService = Depends(get_payment_service),
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's payments.
    
    Requires JWT authentication.
    
    Returns:
        List of current user's payments
    """
    return await service.list_user_payments(current_user.user_id)


@router.get("/payments/{payment_id}", response_model=PaymentResponse, tags=["payments"])
async def get_payment(
    payment_id: int,
    service: PaymentService = Depends(get_payment_service),
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific payment by ID.
    
    Path parameters:
    - **payment_id**: Payment ID
    
    Requires JWT authentication.
    
    Returns:
        Payment data
        
    Raises:
        404 Not Found: Payment not found
    """
    return await service.get_payment_by_id(payment_id)


@router.put("/payments/{payment_id}", response_model=PaymentResponse, tags=["payments"])
async def update_payment(
    payment_id: int,
    data: PaymentUpdate,
    service: PaymentService = Depends(get_payment_service),
    current_user: User = Depends(get_current_user)
):
    """
    Update a payment.
    
    Path parameters:
    - **payment_id**: Payment ID
    
    Request body:
    - **data**: Payment update data (all fields optional)
    
    Requires JWT authentication.
    
    Returns:
        Updated payment
        
    Raises:
        404 Not Found: Payment not found
    """
    return await service.update_payment(payment_id, data)


@router.delete("/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["payments"])
async def delete_payment(
    payment_id: int,
    service: PaymentService = Depends(get_payment_service),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a payment.
    
    Path parameters:
    - **payment_id**: Payment ID
    
    Requires JWT authentication.
    
    Returns:
        204 No Content on success
        
    Raises:
        404 Not Found: Payment not found
    """
    await service.delete_payment(payment_id)
    return None
