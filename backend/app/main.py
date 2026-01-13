from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.dependencies import connect_to_db, disconnect_from_db
from app.core.router import router as core_router
from app.core import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    await connect_to_db()
    await init_db()
    try:
        yield
    finally:
        # Shutdown logic
        await disconnect_from_db()

app = FastAPI(lifespan=lifespan)

@app.get("/api")
async def read_root():
    return {"message": "Welcome to DabljaAR Backend"}


app.include_router(core_router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)