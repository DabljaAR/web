from datetime import datetime, timezone
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check():
    """
    Simple health check endpoint.
    Returns service status and current UTC timestamp.
    """
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat() + "Z"}