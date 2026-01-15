"""API router for core endpoints."""
from datetime import datetime, timezone
from typing import List
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schema import UserCreate, UserLogin, TokenRefresh, UserLoginResponse, TokenResponse, UserResponse, UserUpdate
from app.core.db import get_db
from app.core.models import User
from app.core.repository import UserRepository
from app.core.auth import AuthService, get_auth_service, get_current_user
from app.core.services import UserService
from app.core.exceptions import UserAlreadyExistsException, InvalidCredentialsException, TokenExpiredException
from app.core.rate_limiter import limiter
from fastapi import Request


router = APIRouter()

# Create uploads directory if it doesn't exist
UPLOAD_DIR = Path("uploads/avatars")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Allowed image extensions
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 5MB


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
@limiter.limit("5/minute")
async def signup(
    request: Request,
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
    except Exception as e:
        # Log the full error for debugging
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        error_detail = str(e)
        logger.error(f"Signup error: {error_detail}", exc_info=True)
        traceback.print_exc()
        # Return detailed error in development, generic in production
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {error_detail}"
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


@router.post("/upload/avatar", tags=["upload"])
async def upload_avatar(file: UploadFile = File(...)):
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
    
    # Read file content
    contents = await file.read()
    
    # Validate file size
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB"
        )
    
    # Generate unique filename
    file_id = str(uuid.uuid4())
    filename = f"{file_id}{file_ext}"
    file_path = UPLOAD_DIR / filename
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(contents)
    
    # Return URL (adjust based on your server setup)
    # For development, use full URL with localhost
    # For production, use full URL with your domain
    import os
    base_url = os.getenv("BASE_URL", "http://localhost:8000")
    file_url = f"{base_url}/uploads/avatars/{filename}"
    
    return {"url": file_url, "filename": filename}


@router.get("/health", tags=["health"])
async def health_check():
    """
    Simple health check endpoint.
    Returns service status and current UTC timestamp.
    """
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat() + "Z"}
