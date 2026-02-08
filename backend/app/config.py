import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

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
    
    # Auth0 / Social configuration
    GOOGLE_REDIRECT_URL: str = os.getenv("GOOGLE_REDIRECT_URL", "")
    FACEBOOK_REDIRECT_URL: str = os.getenv("FACEBOOK_REDIRECT_URL", "")
    AUTH0_DOMAIN: str = os.getenv("AUTH0_DOMAIN", "")
    AUTH0_CLIENT_ID: str = os.getenv("AUTH0_CLIENT_ID", "")
    AUTH0_CLIENT_SECRET: str = os.getenv("AUTH0_CLIENT_SECRET", "")
    AUTH0_AUDIENCE: str = os.getenv("AUTH0_AUDIENCE", "")

    # MinIO / S3 Configuration
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "dablaja-minio:9000")

    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    MINIO_BUCKET_NAME: str = os.getenv("MINIO_BUCKET_NAME", "dablaja-videos")
    MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "False").lower() == "true"

    

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
        extra = "ignore"



settings = Settings()

# Note: Required environment variables:
# - DATABASE_URL: PostgreSQL connection string
# - SECRET_KEY or JWT_SECRET: Secret key for JWT token signing (should be a strong random string)
# Optional:
# - ALGORITHM: JWT algorithm (default: HS256)
# - ACCESS_TOKEN_EXPIRE_MINUTES: Access token expiration in minutes (default: 15)
# - REFRESH_TOKEN_EXPIRE_DAYS: Refresh token expiration in days (default: 7)





# Note: Required environment variables:
# - DATABASE_URL: PostgreSQL connection string
# - SECRET_KEY or JWT_SECRET: Secret key for JWT token signing (should be a strong random string)
# Optional:
# - ALGORITHM: JWT algorithm (default: HS256)
# - ACCESS_TOKEN_EXPIRE_MINUTES: Access token expiration in minutes (default: 15)
# - REFRESH_TOKEN_EXPIRE_DAYS: Refresh token expiration in days (default: 7)



