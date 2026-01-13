"""API router for core endpoints."""
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schema import UserCreate, UserLogin, TokenRefresh, UserLoginResponse, TokenResponse, UserResponse, UserUpdate
from app.core.db import get_db
from app.core.models import User
from app.core.repository import UserRepository
from app.core.auth import AuthService, get_auth_service, get_current_user
from app.core.services import UserService
from app.core.exceptions import UserAlreadyExistsException, InvalidCredentialsException, TokenExpiredException


router = APIRouter()


def get_user_service(
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service)
) -> UserService:
    """
    Dependency injection factory for UserService.
    
    Args:
        db: Database session (injected)
        auth_service: AuthService instance (injected)
        
    Returns:
        UserService instance with injected dependencies
    """
    user_repo = UserRepository(db, User)
    return UserService(user_repo, auth_service)


@router.post("/signup", response_model=dict, status_code=status.HTTP_201_CREATED, tags=["auth"])
async def signup(
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service)
):
    """
    Register a new user.
    
    - **username**: Unique username (3-50 characters)
    - **email**: Valid email address
    - **password**: Password (min 8 chars, must contain uppercase, lowercase, and digit)
    - **first_name**: Optional first name
    - **last_name**: Optional last name
    - **preferred_language**: Optional language code
    - **avatar_url**: Optional avatar URL
    
    Returns created user data.
    """
    try:
        user = await user_service.signup(user_data)
        return {"message": "User created successfully", "user": user.model_dump()}
    except UserAlreadyExistsException as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e.detail)
        )


@router.post("/login", response_model=UserLoginResponse, tags=["auth"])
async def login(
    login_data: UserLogin,
    user_service: UserService = Depends(get_user_service)
):
    """
    Authenticate user and get access/refresh tokens.
    
    - **username**: Username or email
    - **password**: User password
    
    Returns access token, refresh token, and user information.
    """
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


@router.get("/health", tags=["health"])
async def health_check():
    """
    Simple health check endpoint.
    Returns service status and current UTC timestamp.
    """
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat() + "Z"}
