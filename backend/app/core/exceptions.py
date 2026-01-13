"""Custom exceptions for the core module."""

from fastapi import HTTPException, status


class UserAlreadyExistsException(HTTPException):
    """Exception raised when trying to create a user that already exists."""
    
    def __init__(self, detail: str = "User already exists"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            headers=None
        )


class InvalidCredentialsException(HTTPException):
    """Exception raised when authentication credentials are invalid."""
    
    def __init__(self, detail: str = "Invalid credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )


class TokenExpiredException(HTTPException):
    """Exception raised when a JWT token has expired."""
    
    def __init__(self, detail: str = "Token has expired"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"}
        )
