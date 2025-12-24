from databases import Database
from app.config import settings

database = Database(settings.DATABASE_URL)

async def connect_to_db():
    await database.connect()

async def disconnect_from_db():
    await database.disconnect()