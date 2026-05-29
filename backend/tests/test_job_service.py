"""Unit tests for JobService using an in-memory SQLite database."""
import asyncio
import pytest
import pytest_asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
# Import all models so Base.metadata knows about every FK-referenced table
import app.core.models  # noqa: F401
import app.core.video_model  # noqa: F401
from app.jobs.models import JobType, JobStatus
from app.jobs.schemas import JobCreate, JobUpdate
from app.jobs.service import JobService

# ---------------------------------------------------------------------------
# Engine shared across the whole test module (StaticPool keeps one connection
# so all sessions share the same in-memory database).
# ---------------------------------------------------------------------------
DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_engine = create_async_engine(
    DATABASE_URL,
    poolclass=StaticPool,
    connect_args={"check_same_thread": False},
)
_SessionFactory = async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="module")
async def setup_db():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db(setup_db):  # noqa: ARG001
    async with _SessionFactory() as session:
        yield session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_job(db):
    service = JobService(db)
    job_in = JobCreate(
        video_id=str(uuid4()),
        user_id=1,
        job_type=JobType.VIDEO_PROCESS,
        status=JobStatus.QUEUED,
        progress=0.0,
    )
    job = await service.create_job(job_in)
    assert job.id is not None

    fetched = await service.get_job(job.id)
    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.job_type == JobType.VIDEO_PROCESS


@pytest.mark.asyncio
async def test_update_job(db):
    service = JobService(db)
    job_in = JobCreate(
        video_id=str(uuid4()),
        user_id=2,
        job_type=JobType.VIDEO_HLS,
        status=JobStatus.QUEUED,
        progress=0.0,
    )
    job = await service.create_job(job_in)

    updated = await service.update_job(job.id, JobUpdate(progress=50.0, status=JobStatus.PROCESSING))
    assert updated is not None
    assert updated.progress == 50.0
    assert updated.status == JobStatus.PROCESSING


@pytest.mark.asyncio
async def test_list_jobs(db):
    service = JobService(db)
    jobs = await service.list_jobs()
    assert isinstance(jobs, list)


@pytest.mark.asyncio
async def test_cancel_job(db):
    service = JobService(db)
    job_in = JobCreate(
        video_id=str(uuid4()),
        user_id=3,
        job_type=JobType.STT_TRANSCRIBE,
        status=JobStatus.QUEUED,
        progress=0.0,
    )
    job = await service.create_job(job_in)
    cancelled = await service.cancel_job(job.id)
    assert cancelled is not None
    assert cancelled.status == JobStatus.CANCELLED


@pytest.mark.asyncio
async def test_update_job_progress(db):
    service = JobService(db)
    job_in = JobCreate(
        video_id=str(uuid4()),
        user_id=4,
        job_type=JobType.NMT_TRANSLATE,
        status=JobStatus.QUEUED,
        progress=0.0,
    )
    job = await service.create_job(job_in)
    updated = await service.update_job_progress(
        job.id, 80.0, JobStatus.PROCESSING, "No error"
    )
    assert updated is not None
    assert updated.progress == 80.0
    assert updated.status == JobStatus.PROCESSING
    assert updated.error_message == "No error"


@pytest.mark.asyncio
async def test_get_nonexistent_job(db):
    service = JobService(db)
    result = await service.get_job("nonexistent-id")
    assert result is None
