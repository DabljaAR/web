from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/dabljaar"
    
    # JWT Authentication
    SECRET_KEY: str = "your-secret-key-change-this-in-production"  # Should be set via env var: JWT_SECRET
    ALGORITHM: str = "HS256"  # JWT signing algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # Access token expiration (15 minutes)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # Refresh token expiration (7 days)
    

        # Logging Configuration
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_DIR: str = "logs"  # Directory for log files
    LOG_FILE: str = "app.log"  # Main log file name
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10MB - max size before rotation
    LOG_BACKUP_COUNT: int = 5  # Number of backup log files to keep
    LOG_ENABLE_CONSOLE: bool = True  # Enable console logging
    LOG_ENABLE_FILE: bool = True  # Enable file logging
    LOG_JSON_FORMAT: bool = False  # Use JSON format for logs
    LOG_ENABLE_SUCCESS: bool = True  # Enable success request logging (2xx status codes)
   


   
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



