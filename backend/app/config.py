from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

# Load environment variables from a .env file
load_dotenv()

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/dabljaar")

settings = Settings()