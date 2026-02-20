"""Integration tests for the job API router (app/api/job_router.py).

Uses an in-memory SQLite database via ASGI transport so no running server or
real PostgreSQL connection is required.
"""
import asyncio
import pytest
import pytest_asyncio
from uuid import uuid4

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── must import all models before create_all ──────────────────────────────
from app.core.db import Base
import app.core.models  # noqa: F401
import app.media.models  # noqa: F401
import app.jobs.models  # noqa: F401
# ──────────────────────────────────────────────────────────────────────────

from app.main import app
from app.core.db import get_db
from app.core.auth import get_current_user
from app.jobs.models import Job, JobStatus, JobType


# ---------------------------------------------------------------------------
# Shared event loop for the module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# In-memory SQLite engine + session factory
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="module")
async def engine():
    eng = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture(scope="module")
async def async_session_factory(engine):
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Fake user injected via dependency override
# ---------------------------------------------------------------------------

class _FakeUser:
    user_id = 1
    username = "testuser"
    email = "test@example.com"
    is_active = True


FAKE_USER = _FakeUser()


# ---------------------------------------------------------------------------
# ASGI test client with overridden dependencies
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="module")
async def client(async_session_factory):
    """AsyncClient wired to the FastAPI app with mocked DB and auth."""

    async def override_get_db():
        async with async_session_factory() as session:
            yield session

    async def override_get_current_user():
        return FAKE_USER

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: insert a job row directly into the test DB
# ---------------------------------------------------------------------------

async def _create_job(
    session_factory,
    *,
    job_type: JobType = JobType.VIDEO_PROCESS,
    status: JobStatus = JobStatus.QUEUED,
    user_id: int = 1,
) -> Job:
    video_id = str(uuid4())
    job = Job(
        id=str(uuid4()),
        video_id=video_id,
        user_id=user_id,
        job_type=job_type,
        status=status,
        progress=0.0,
        retry_count=0,
        max_retries=3,
    )
    from datetime import datetime
    job.created_at = datetime.utcnow()
    job.updated_at = datetime.utcnow()

    async with session_factory() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
    return job


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_job_not_found(client):
    resp = await client.get("/api/jobs/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_job_success(client, async_session_factory):
    job = await _create_job(async_session_factory)
    resp = await client.get(f"/api/jobs/{job.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == job.id
    assert data["status"] == JobStatus.QUEUED.value


@pytest.mark.asyncio
async def test_get_job_forbidden(client, async_session_factory):
    """A job belonging to a different user should return 403."""
    job = await _create_job(async_session_factory, user_id=999)
    resp = await client.get(f"/api/jobs/{job.id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_my_jobs(client, async_session_factory):
    await _create_job(async_session_factory)
    await _create_job(async_session_factory)
    resp = await client.get("/api/jobs/")
    assert resp.status_code == 200
    jobs = resp.json()
    assert isinstance(jobs, list)
    assert len(jobs) >= 2
    # All returned jobs should belong to the fake user
    assert all(j["user_id"] == FAKE_USER.user_id for j in jobs)


@pytest.mark.asyncio
async def test_list_jobs_for_video(client, async_session_factory):
    job = await _create_job(async_session_factory)
    resp = await client.get(f"/api/jobs/video/{job.video_id}")
    assert resp.status_code == 200
    jobs = resp.json()
    assert any(j["id"] == job.id for j in jobs)


@pytest.mark.asyncio
async def test_cancel_job_success(client, async_session_factory):
    job = await _create_job(async_session_factory, status=JobStatus.QUEUED)
    resp = await client.post(f"/api/jobs/{job.id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == JobStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_cancel_job_already_completed(client, async_session_factory):
    job = await _create_job(async_session_factory, status=JobStatus.COMPLETED)
    resp = await client.post(f"/api/jobs/{job.id}/cancel")
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_job_progress(client, async_session_factory):
    job = await _create_job(async_session_factory, status=JobStatus.PROCESSING)
    payload = {"progress": 55.0, "status": "PROCESSING"}
    resp = await client.patch(f"/api/jobs/{job.id}/progress", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["progress"] == 55.0


@pytest.mark.asyncio
async def test_update_job_progress_not_found(client):
    payload = {"progress": 10.0}
    resp = await client.patch("/api/jobs/does-not-exist/progress", json=payload)
    assert resp.status_code == 404
