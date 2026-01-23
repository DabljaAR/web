from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

# Load environment variables from a .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    DATABASE_URL: str = os.getenv(
            "DATABASE_URL", 
            "postgresql+asyncpg://postgres:postgres@localhost:5432/dabljaar"
        )
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    
    # Note: os.getenv returns strings, so we must cast to int
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 15))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 7))
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

# Note: Required environment variables:
# - DATABASE_URL: PostgreSQL connection string
# - SECRET_KEY or JWT_SECRET: Secret key for JWT token signing (should be a strong random string)
# Optional:
# - ALGORITHM: JWT algorithm (default: HS256)
# - ACCESS_TOKEN_EXPIRE_MINUTES: Access token expiration in minutes (default: 15)
# - REFRESH_TOKEN_EXPIRE_DAYS: Refresh token expiration in days (default: 7)



