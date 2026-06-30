"""JWT authentication and token management."""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.repository import UserRepository
from app.core.models import User
from app.core.db import get_db
from app.core.exceptions import InvalidCredentialsException, TokenExpiredException

import httpx
import logging

logger = logging.getLogger(__name__)


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


BCRYPT_MAX_PASSWORD_BYTES = 72


class PasswordValidationError(ValueError):
    """Raised when password input violates validation constraints."""


def _validate_bcrypt_password_length(password: str) -> None:
    """Validate password byte length against bcrypt backend limits."""
    password_bytes = len(password.encode("utf-8"))
    if password_bytes > BCRYPT_MAX_PASSWORD_BYTES:
        raise PasswordValidationError(
            f"Password is too long for secure hashing. Max {BCRYPT_MAX_PASSWORD_BYTES} UTF-8 bytes."
        )


class AuthService:
    """JWT authentication service with dependency injection."""
    
    def __init__(self, user_repo: UserRepository):
        """
        Initialize AuthService with UserRepository dependency injection.
        
        Args:
            user_repo: UserRepository instance for user data access
        """
        self.user_repo = user_repo
        self.secret_key = settings.SECRET_KEY
        self.algorithm = settings.ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a plain password against a hashed password.
        
        Args:
            plain_password: The plain text password to verify
            hashed_password: The hashed password to compare against
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except ValueError:
            # Invalid plain password format for bcrypt backend limits.
            return False
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """
        Hash a password using bcrypt.
        
        Args:
            password: The plain text password to hash
            
        Returns:
            The hashed password
        """
        _validate_bcrypt_password_length(password)
        return pwd_context.hash(password)
    
    def create_access_token(self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """
        Create a JWT access token.
        
        Args:
            data: Dictionary containing the data to encode in the token
            expires_delta: Optional timedelta for token expiration. 
                          If not provided, uses default from settings.
            
        Returns:
            Encoded JWT token string
        """
        to_encode = data.copy()
        
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=self.access_token_expire_minutes)
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """
        Create a JWT refresh token.
        
        Args:
            data: Dictionary containing the data to encode in the token
            
        Returns:
            Encoded JWT refresh token string
        """
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=self.refresh_token_expire_days)
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt
    
    def decode_token(self, token: str, token_type: str = "access") -> Dict[str, Any]:
        """
        Decode and validate a JWT token.
        
        Args:
            token: The JWT token to decode
            token_type: Expected token type ("access" or "refresh")
            
        Returns:
            Decoded token payload
            
        Raises:
            TokenExpiredException: If the token has expired
            InvalidCredentialsException: If the token is invalid or wrong type
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Verify token type
            if payload.get("type") != token_type:
                raise InvalidCredentialsException("Invalid token type")
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise TokenExpiredException("Token has expired")
        except JWTError:
            raise InvalidCredentialsException("Could not validate token")
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate a user by username/email and password.
        
        Args:
            username: Username or email
            password: Plain text password
            
        Returns:
            User object if authentication successful, None otherwise
        """
        # Try to get user by username first
        user = await self.user_repo.get_by_username(username)
        
        # If not found, try by email
        if not user:
            user = await self.user_repo.get_by_email(username)
        
        if not user:
            return None
        
        if not self.verify_password(password, user.password):
            return None
        
        return user
    
    @staticmethod
    async def verify_google_token(credential: str) -> Dict[str, Any]:
        """Verify Google ID token and return the payload."""
        if not settings.GOOGLE_CLIENT_ID:
            raise InvalidCredentialsException("Google authentication is not configured on the server")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"id_token": credential},
                )
                response.raise_for_status()
                token_info = response.json()
        except httpx.HTTPStatusError:
            raise InvalidCredentialsException("Invalid Google token")
        except httpx.RequestError:
            raise InvalidCredentialsException("Failed to verify Google token")

        if token_info.get("aud") != settings.GOOGLE_CLIENT_ID:
            logger.warning("Google token audience mismatch: expected=%s got=%s", settings.GOOGLE_CLIENT_ID, token_info.get("aud"))
            raise InvalidCredentialsException("Google token audience mismatch")

        return token_info

    def create_token_pair(self, user: User) -> Dict[str, str]:
        """
        Create both access and refresh tokens for a user.
        
        Args:
            user: User object to create tokens for
            
        Returns:
            Dictionary containing access_token and refresh_token
        """
        token_data = {
            "sub": user.username,
            "user_id": user.user_id,
            "email": user.email
        }
        
        access_token = self.create_access_token(data=token_data)
        refresh_token = self.create_refresh_token(data=token_data)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }
    
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, str]:
        """
        Generate a new access token from a refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            Dictionary containing new access_token and refresh_token (rotated)
            
        Raises:
            InvalidCredentialsException: If refresh token is invalid
            TokenExpiredException: If refresh token has expired
        """
        # Decode and validate refresh token
        payload = self.decode_token(refresh_token, token_type="refresh")
        username: str = payload.get("sub")
        
        if username is None:
            raise InvalidCredentialsException("Invalid refresh token")
        
        # Get user to verify they still exist
        user = await self.user_repo.get_by_username(username)
        if not user:
            raise InvalidCredentialsException("User not found")
        
        # Create new token pair (refresh token rotation)
        token_data = {
            "sub": user.username,
            "user_id": user.user_id,
            "email": user.email
        }
        
        new_access_token = self.create_access_token(data=token_data)
        new_refresh_token = self.create_refresh_token(data=token_data)
        
        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        }


# Dependency injection helpers
def get_auth_service(
    db: AsyncSession = Depends(get_db)
) -> AuthService:
    """
    Dependency injection factory for AuthService.
    
    Args:
        db: Database session
        
    Returns:
        AuthService instance with injected UserRepository
    """
    from app.core.models import User
    user_repo = UserRepository(db, User)
    return AuthService(user_repo)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    auth_service: AuthService = Depends(get_auth_service)
) -> User:
    """
    Get the current authenticated user from JWT token.
    
    Args:
        token: JWT access token from request header
        auth_service: AuthService instance (injected)
        
    Returns:
        Current authenticated User object
        
    Raises:
        InvalidCredentialsException: If token is invalid or user not found
    """
    payload = auth_service.decode_token(token, token_type="access")
    username: str = payload.get("sub")

    if username is None:
        raise InvalidCredentialsException("Could not validate credentials")

    user = await auth_service.user_repo.get_by_username(username)
    if user is None:
        raise InvalidCredentialsException("User not found")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Get the current active user (additional check for active status).

    Args:
        current_user: Current user from get_current_user dependency

    Returns:
        Current active User object

    Raises:
        HTTPException: If user is inactive
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")
    return current_user
