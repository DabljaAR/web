import asyncio
import uuid
import sys
import os
import json
from datetime import datetime
from sqlalchemy import select

# Ensure project root is in path
sys.path.append(os.getcwd())

from app.core.db import AsyncSessionLocal
from app.media.models import Video, VideoStatus
from app.jobs.models import Job, JobType, JobStatus
from app.core.models import User
from app.jobs.celery_app import celery_app

async def trigger_nmt_manual():
    print("🚀 Manual NMT Test Trigger (Double Task Mode)")
    
    # 1. Load STT Data
    stt_path = "stt_output.json"
    if not os.path.exists(stt_path):
        print(f"❌ Error: {stt_path} not found. Please create it first.")
        return
        
    with open(stt_path, "r") as f:
        stt_output = json.load(f)
    print(f"✅ Loaded STT data from {stt_path}")

    # 2. Check Redis
    import redis
    from app.config import settings
    try:
        r = redis.from_url(settings.CELERY_BROKER_URL)
        r.ping()
        print(f"✅ Redis is alive at {settings.CELERY_BROKER_URL}")
    except Exception as e:
        print(f"❌ Redis is NOT running: {e}")
        return

    async with AsyncSessionLocal() as db:
        # Get/Create User
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if not user:
            print("Creating temporary user...")
            user = User(username="nmt_tester", email="nmt@test.com", password="hashed_password", first_name="Tester")
            db.add(user)
            await db.flush()
        
        # Create Video
        video_id = str(uuid.uuid4())
        video = Video(
            id=video_id,
            user_id=user.user_id,
            title="Lecture NMT Dual Test",
            original_filename="lecture.mp4",
            file_path="uploads/lecture.mp4",
            status=VideoStatus.COMPLETED
        )
        db.add(video)
        await db.flush()
        print(f"✅ Created Video ID: {video_id}")

        # 3. Trigger Two Tasks
        for trigger_tts in [True, False]:
            mode_str = "WITH TTS" if trigger_tts else "NO TTS"
            print(f"\n--- Initiating NMT ({mode_str}) ---")
            
            # Create NMT Job Row
            job_id = str(uuid.uuid4())
            job = Job(
                id=job_id,
                video_id=video_id,
                user_id=user.user_id,
                job_type=JobType.NMT_TRANSLATE,
                status=JobStatus.QUEUED,
                input_data={
                    "target_lang": "ar",
                    "stt_data": stt_output,
                    "trigger_tts": trigger_tts
                }
            )
            db.add(job)
            await db.commit() # Commit each to ensure they are visible
            
            # Prepare Payload
            trigger_data = stt_output.copy()
            trigger_data["job_id"] = job_id
            trigger_data["video_id"] = video_id
            trigger_data["transcript_key"] = video.file_path
            trigger_data["trigger_tts"] = trigger_tts # This is also in the payload for pipeline compatibility

            # Dispatch
            print(f"📦 Dispatching nmt_translate for job {job_id}...")
            celery_app.send_task(
                "app.jobs.tasks.pipeline.nmt_translate",
                args=[trigger_data],
                kwargs={"target_lang": "ar", "trigger_tts": trigger_tts},
                queue="ai_nmt"
            )
            print(f"✨ SUCCESS! {mode_str} task pushed.")

    print("\n🏁 Both tasks dispatched. Watch your worker logs.")

if __name__ == "__main__":
    asyncio.run(trigger_nmt_manual())
