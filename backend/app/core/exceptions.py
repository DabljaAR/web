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


class SubscriptionPlanNotFound(HTTPException):
    def __init__(self, detail: str = "Subscription plan not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class UserSubscriptionNotFound(HTTPException):
    def __init__(self, detail: str = "User subscription not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class PaymentNotFound(HTTPException):
    def __init__(self, detail: str = "Payment not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class RecipeNotFound(HTTPException):
    def __init__(self, detail: str = "Recipe not found"):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


class SubscriptionPlanAlreadyExists(HTTPException):
    def __init__(self, detail: str = "Subscription plan already exists"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class UserSubscriptionAlreadyExists(HTTPException):
    def __init__(self, detail: str = "User subscription already exists"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class PaymentAlreadyExists(HTTPException):
    def __init__(self, detail: str = "Payment already exists"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class RecipeAlreadyExists(HTTPException):
    def __init__(self, detail: str = "Recipe already exists"):
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)
