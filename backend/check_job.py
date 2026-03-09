import asyncio
import sys
import os
from sqlalchemy import select

# Ensure project root is in path
sys.path.append(os.getcwd())

from app.core.db import AsyncSessionLocal
from app.jobs.models import Job
import app.media.models

async def check_jobs():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Job).order_by(Job.created_at.desc()).limit(10))
        jobs = result.scalars().all()
        print(f"--- Recent Jobs (Top 10) ---")
        for job in jobs:
            print(f"{job.id} | {job.job_type.value:20} | {job.status.value:12} | Parent: {job.parent_job_id or 'None'}")

if __name__ == "__main__":
    asyncio.run(check_jobs())
