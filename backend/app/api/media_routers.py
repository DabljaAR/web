import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter, BackgroundTasks, Body, Depends, File, Form,
    HTTPException, Query, UploadFile, status,
)
from sqlalchemy import and_, exists, or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.db import get_db
from app.core.models import User
from app.jobs.models import Job, JobStatus, JobType
from app.media_service.client import MediaServiceClient
from app.media_service.schemas import (
    DashboardResponse, PaginatedVideoResponse, VideoResponse, VideoUploadResponse,
)
from app.tasks.models import VideoTask
from app.shared.processing_mode import resolve_processing_mode
from app.jobs.tasks.processing import process_video_task, process_video_hls_task, download_youtube_task

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/videos",
    tags=["Media"],
    dependencies=[Depends(get_current_user)],
)

_MEDIA_SVC = lambda: os.getenv("MEDIA_SERVICE_URL", "http://media-service:8001")  # noqa: E731


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _save_upload_to_tempfile(file: UploadFile) -> Path:
    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
        return Path(tmp.name)


async def _enrich_video(
    v: dict,
    client: MediaServiceClient,
    jobs_by_video: dict,
    latest_task_by_video: dict,
) -> dict:
    """Add presigned URLs and job-state fields to a video dict in-place."""
    dubbed_path = v.get("dubbed_video_path")
    display_key = dubbed_path or v.get("file_path") or ""

    if display_key:
        try:
            v["url"] = await client.presign_url(display_key)
        except Exception:
            v["url"] = None
    if dubbed_path:
        try:
            v["dubbed_video_url"] = await client.presign_url(dubbed_path)
        except Exception:
            v["dubbed_video_url"] = None
    if v.get("thumbnail_path"):
        try:
            v["thumbnail_url"] = await client.presign_url(v["thumbnail_path"])
        except Exception:
            v["thumbnail_url"] = None
    if v.get("audio_path"):
        try:
            v["audio_url"] = await client.presign_url(v["audio_path"])
        except Exception:
            v["audio_url"] = None

    video_id = v["id"]
    page_jobs = jobs_by_video.get(video_id, [])
    latest_task = latest_task_by_video.get(video_id)

    active_statuses = [JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.RETRYING]
    scoped_active = [
        j for j in page_jobs
        if j.status in active_statuses
        and (
            not latest_task
            or not latest_task.root_job_id
            or j.id == latest_task.root_job_id
            or j.parent_job_id == latest_task.root_job_id
        )
    ]
    completed_jobs = [j for j in page_jobs if j.status == JobStatus.COMPLETED]

    v["has_active_job"] = bool(scoped_active)
    if scoped_active:
        newest = scoped_active[0]
        v["active_job_status"] = newest.status.value
        v["active_job_progress"] = max((j.progress or 0.0) for j in scoped_active)
    else:
        v["active_job_status"] = None
        v["active_job_progress"] = 0.0

    transcript_url = None
    translation_url = None
    for job in completed_jobs:
        if not job.output_data:
            continue
        if job.job_type == JobType.STT_TRANSCRIBE:
            segs = job.output_data.get("segments")
            if isinstance(segs, list) and segs:
                if not transcript_url:
                    transcript_url = f"/jobs/{job.id}/preview?kind=transcript"
                if not translation_url and (
                    job.output_data.get("translated_transcript")
                    or any(s.get("translated_text") for s in segs)
                ):
                    translation_url = f"/jobs/{job.id}/preview?kind=translation"
        if not translation_url and job.job_type == JobType.NMT_TRANSLATE:
            if isinstance(job.output_data.get("segments"), list) and job.output_data["segments"]:
                translation_url = f"/jobs/{job.id}/preview?kind=translation"
        if transcript_url and translation_url:
            break

    v["transcript_url"] = transcript_url
    v["translation_url"] = translation_url
    return v


async def _fetch_job_enrichments(
    db: AsyncSession,
    video_ids: list[str],
) -> tuple[dict, dict]:
    jobs_by_video: dict = {}
    if video_ids:
        res = await db.execute(
            select(Job).where(Job.video_id.in_(video_ids)).order_by(Job.created_at.desc())
        )
        for job in res.scalars().all():
            jobs_by_video.setdefault(job.video_id, []).append(job)

    latest_task_by_video: dict = {}
    if video_ids:
        res = await db.execute(
            select(VideoTask)
            .where(VideoTask.video_id.in_(video_ids))
            .order_by(VideoTask.video_id.asc(), VideoTask.created_at.desc())
        )
        for task in res.scalars().all():
            if task.video_id not in latest_task_by_video:
                latest_task_by_video[task.video_id] = task

    return jobs_by_video, latest_task_by_video


# ---------------------------------------------------------------------------
# Upload endpoints
# ---------------------------------------------------------------------------

@router.post("/upload", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    output_type: str = Form("fullDubbing"),
    domain: str = Form("general"),
    voice: str = Form("male1"),
    translation_style: str = Form("neutral"),
    current_user: User = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Expected video.")

    video_id = str(uuid.uuid4())
    ext = Path(file.filename or "video.mp4").suffix or ".mp4"
    file_key = f"videos/{current_user.user_id}/{video_id}{ext}"

    tmp_path = await _save_upload_to_tempfile(file)
    try:
        client = MediaServiceClient()
        await client.upload_file(tmp_path, key=file_key, content_type=file.content_type)
    finally:
        tmp_path.unlink(missing_ok=True)

    video_data = await client.create_video({
        "id": video_id,
        "user_id": current_user.user_id,
        "title": file.filename or "Untitled",
        "original_filename": file.filename or "upload",
        "file_path": file_key,
        "media_type": "VIDEO",
        "status": "PENDING",
        "size_bytes": file.size,
    })

    options = {
        "output_type": output_type,
        "domain": domain,
        "voice": voice,
        "translation_style": translation_style,
    }
    background_tasks.add_task(process_video_task, video_id, file_key, options=options)
    return VideoUploadResponse(id=video_data["id"], status=video_data["status"])


@router.post("/upload/audio", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    output_type: str = Form("fullDubbing"),
    domain: str = Form("general"),
    voice: str = Form("male1"),
    translation_style: str = Form("neutral"),
    current_user: User = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Expected audio.")
    filename = (file.filename or "").lower()
    if filename.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
        raise HTTPException(status_code=400, detail="Invalid file extension. Expected audio file.")

    video_id = str(uuid.uuid4())
    ext = Path(file.filename or "audio.mp3").suffix or ".mp3"
    file_key = f"audio/{current_user.user_id}/{video_id}{ext}"

    tmp_path = await _save_upload_to_tempfile(file)
    try:
        client = MediaServiceClient()
        await client.upload_file(tmp_path, key=file_key, content_type=file.content_type)
    finally:
        tmp_path.unlink(missing_ok=True)

    video_data = await client.create_video({
        "id": video_id,
        "user_id": current_user.user_id,
        "title": file.filename or "Untitled",
        "original_filename": file.filename or "upload",
        "file_path": file_key,
        "media_type": "AUDIO",
        "status": "PENDING",
        "size_bytes": file.size,
    })

    options = {
        "output_type": output_type,
        "domain": domain,
        "voice": voice,
        "translation_style": translation_style,
    }
    background_tasks.add_task(process_video_task, video_id, file_key, options=options)
    return VideoUploadResponse(id=video_data["id"], status=video_data["status"])


@router.post("/upload/text", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_text(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    output_type: str = Form("fullDubbing"),
    domain: str = Form("general"),
    voice: str = Form("male1"),
    translation_style: str = Form("neutral"),
    current_user: User = Depends(get_current_user),
):
    fname = (file.filename or "").lower()
    ct = file.content_type or ""
    if ct.startswith("video/") or ct.startswith("audio/"):
        raise HTTPException(status_code=400, detail="Invalid file type. Expected text.")
    if not (ct.startswith("text/") or fname.endswith(".txt")):
        raise HTTPException(status_code=400, detail="Invalid file type. Expected text.")

    video_id = str(uuid.uuid4())
    ext = Path(file.filename or "doc.txt").suffix or ".txt"
    file_key = f"text/{current_user.user_id}/{video_id}{ext}"

    tmp_path = await _save_upload_to_tempfile(file)
    try:
        client = MediaServiceClient()
        await client.upload_file(tmp_path, key=file_key, content_type=ct or "text/plain")
    finally:
        tmp_path.unlink(missing_ok=True)

    video_data = await client.create_video({
        "id": video_id,
        "user_id": current_user.user_id,
        "title": file.filename or "Untitled",
        "original_filename": file.filename or "upload",
        "file_path": file_key,
        "media_type": "TEXT",
        "status": "COMPLETED",
        "size_bytes": file.size,
    })
    return VideoUploadResponse(id=video_data["id"], status=video_data["status"])


@router.post("/upload/youtube", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_from_youtube(
    background_tasks: BackgroundTasks,
    youtube_url: str = Form(...),
    format: str = Form("video"),
    quality: str = Form("720p"),
    output_type: str = Form("uploadOnly"),
    domain: str = Form("general"),
    voice: str = Form("male1"),
    translation_style: str = Form("neutral"),
    current_user: User = Depends(get_current_user),
):
    try:
        import yt_dlp
        import asyncio

        ydl_opts = {"quiet": True, "skip_download": True, "noplaylist": True}

        def _check():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(youtube_url, download=False)

        info = await asyncio.to_thread(_check)
        if not info:
            raise HTTPException(status_code=400, detail="Video not found or unavailable.")
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=f"Video not found or unavailable: {e}")

    media_type = "AUDIO" if format == "audio" else "VIDEO"
    video_id = str(uuid.uuid4())
    client = MediaServiceClient()
    video_data = await client.create_video({
        "id": video_id,
        "user_id": current_user.user_id,
        "title": info.get("title", "YouTube Video"),
        "original_filename": "youtube",
        "file_path": "",
        "media_type": media_type,
        "status": "PENDING",
    })

    options = {
        "output_type": output_type,
        "domain": domain,
        "voice": voice,
        "translation_style": translation_style,
    }
    background_tasks.add_task(
        download_youtube_task, video_id, current_user.user_id, youtube_url, format, quality, options
    )
    return VideoUploadResponse(id=video_data["id"], status=video_data["status"])


@router.post("/upload/hls", response_model=VideoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_video_hls(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Invalid file type.")

    video_id = str(uuid.uuid4())
    ext = Path(file.filename or "video.mp4").suffix or ".mp4"
    file_key = f"videos/{current_user.user_id}/source/{video_id}{ext}"

    tmp_path = await _save_upload_to_tempfile(file)
    try:
        client = MediaServiceClient()
        await client.upload_file(tmp_path, key=file_key, content_type=file.content_type)
    finally:
        tmp_path.unlink(missing_ok=True)

    video_data = await client.create_video({
        "id": video_id,
        "user_id": current_user.user_id,
        "title": file.filename or "Untitled",
        "original_filename": file.filename or "upload",
        "file_path": file_key,
        "media_type": "VIDEO",
        "status": "PENDING",
        "size_bytes": file.size,
    })

    background_tasks.add_task(process_video_hls_task, video_id, file_key)
    return VideoUploadResponse(id=video_data["id"], status=video_data["status"])


# ---------------------------------------------------------------------------
# Reprocess
# ---------------------------------------------------------------------------

@router.post("/{video_id}/reprocess", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_video(
    video_id: str,
    payload: Optional[dict] = Body(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = MediaServiceClient()
    video_data = await client.get_video(video_id)
    if not video_data:
        raise HTTPException(status_code=404, detail="Media not found")
    if video_data["user_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to process this media")

    media_type = (video_data.get("media_type") or "").upper()
    if media_type not in ("VIDEO", "AUDIO"):
        raise HTTPException(status_code=400, detail="Only video/audio can be reprocessed")

    opts = payload or {}
    target_lang = opts.get("target_lang", "arb_Arab")
    output_type = opts.get("output_type", "fullDubbing")
    processing_mode = resolve_processing_mode(output_type)

    from app.tasks.models import VideoTask, TaskStatus
    video_task = VideoTask(
        id=str(uuid.uuid4()),
        video_id=video_id,
        user_id=current_user.user_id,
        source_lang=opts.get("source_lang"),
        target_lang=target_lang,
        output_type=output_type,
        processing_mode=processing_mode,
        num_beams=int(opts.get("num_beams", 5)),
        english_ratio_threshold=float(opts.get("english_ratio_threshold", 0.5)),
        status=TaskStatus.QUEUED,
    )
    db.add(video_task)
    await db.flush()

    audio_key = video_data.get("audio_path") or video_data.get("file_path") or ""
    stt_job = Job(
        id=str(uuid.uuid4()),
        video_id=video_id,
        user_id=current_user.user_id,
        job_type=JobType.STT_TRANSCRIBE,
        status=JobStatus.QUEUED,
        input_data={
            **opts,
            "task_id": video_task.id,
            "audio_key": audio_key,
            "target_lang": target_lang,
            "processing_mode": processing_mode,
        },
    )
    db.add(stt_job)
    video_task.root_job_id = stt_job.id
    await db.commit()
    await db.refresh(stt_job)

    from app.jobs.tasks.pipeline import stt_transcribe
    celery_result = stt_transcribe.apply_async(
        kwargs={"job_id": stt_job.id, "video_id": video_id, "target_lang": target_lang},
        task_id=stt_job.id,
    )
    stt_job.celery_task_id = celery_result.id
    db.add(stt_job)
    await db.commit()

    return {"id": stt_job.id, "status": stt_job.status.value.lower(), "message": "Reprocessing started"}


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("/", response_model=PaginatedVideoResponse)
async def list_videos(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    sort_by: str = Query("date-desc", alias="sortBy"),
    date_range: str = Query("allTime", alias="dateRange"),
    status: Optional[str] = Query(None),
    media_type: Optional[str] = Query(None, alias="mediaType"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = MediaServiceClient()
    raw = await client.list_videos(
        user_id=current_user.user_id,
        page=page,
        limit=limit,
        search=search,
        sort_by=sort_by,
        date_range=date_range,
        status=status,
        media_type=media_type,
    )

    items: list[dict] = raw.get("items", [])
    video_ids = [v["id"] for v in items]
    jobs_by_video, latest_task_by_video = await _fetch_job_enrichments(db, video_ids)

    enriched = []
    for v in items:
        enriched.append(await _enrich_video(v, client, jobs_by_video, latest_task_by_video))

    return {
        "items": enriched,
        "total": raw.get("total", 0),
        "page": raw.get("page", page),
        "size": raw.get("size", limit),
        "pages": raw.get("pages", 0),
        "total_completed": raw.get("total_completed", 0),
        "total_failed": raw.get("total_failed", 0),
    }


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = MediaServiceClient()

    # Active videos (PENDING or PROCESSING)
    active_raw = await client.list_videos(
        user_id=current_user.user_id,
        page=1,
        limit=50,
        status="PENDING,PROCESSING",
    )
    # Active jobs
    res = await db.execute(
        select(Job).where(
            Job.user_id == current_user.user_id,
            Job.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.RETRYING]),
        ).order_by(Job.created_at.desc())
    )
    active_jobs = res.scalars().all()

    active_items = []
    for v in active_raw.get("items", []):
        active_items.append({
            "id": v["id"],
            "video_id": v["id"],
            "name": v.get("title") or v.get("original_filename"),
            "status": v.get("status"),
            "type": "MEDIA_PROCESS",
            "progress": 0.0,
            "created_at": v.get("created_at"),
        })
    for j in active_jobs:
        active_items.append({
            "id": j.id,
            "video_id": j.video_id,
            "name": f"{j.job_type.value}: {j.id[:8]}",
            "status": j.status,
            "type": j.job_type,
            "progress": j.progress,
            "created_at": j.created_at,
        })
    active_items.sort(key=lambda x: x["created_at"] or "", reverse=True)

    # Recent completed/failed videos
    recent_raw = await client.list_videos(
        user_id=current_user.user_id,
        page=1,
        limit=10,
        status="COMPLETED,FAILED",
        sort_by="date-desc",
    )
    recent_video_ids = [v["id"] for v in recent_raw.get("items", [])]
    jobs_by_video: dict = {}
    if recent_video_ids:
        res = await db.execute(
            select(Job).where(Job.video_id.in_(recent_video_ids)).order_by(Job.completed_at.desc())
        )
        for job in res.scalars().all():
            jobs_by_video.setdefault(job.video_id, []).append(job)

    processed_recent = []
    for v in recent_raw.get("items", []):
        dubbed_path = v.get("dubbed_video_path")
        display_key = dubbed_path or v.get("file_path") or ""
        video_entry: dict = {
            "id": v["id"],
            "title": v.get("title"),
            "original_filename": v.get("original_filename"),
            "status": v.get("status"),
            "media_type": v.get("media_type"),
            "created_at": v.get("created_at"),
            "url": None,
            "thumbnail_url": None,
            "audio_url": None,
            "dubbed_video_url": None,
        }
        try:
            if display_key:
                video_entry["url"] = await client.presign_url(display_key)
            if v.get("thumbnail_path"):
                video_entry["thumbnail_url"] = await client.presign_url(v["thumbnail_path"])
            if v.get("audio_path"):
                video_entry["audio_url"] = await client.presign_url(v["audio_path"])
            if dubbed_path:
                video_entry["dubbed_video_url"] = await client.presign_url(dubbed_path)
        except Exception:
            pass

        page_jobs = jobs_by_video.get(v["id"], [])
        video_entry["jobs"] = []
        for j in page_jobs:
            job_entry: dict = {
                "id": j.id,
                "type": j.job_type,
                "status": j.status,
                "completed_at": j.completed_at,
            }
            if j.status == JobStatus.COMPLETED and j.output_data:
                if j.job_type == JobType.STT_TRANSCRIBE and j.output_data.get("segments"):
                    job_entry["transcript_url"] = f"/jobs/{j.id}/preview?kind=transcript"
                    if j.output_data.get("translated_transcript") or any(
                        s.get("translated_text") for s in j.output_data["segments"]
                    ):
                        job_entry["translation_url"] = f"/jobs/{j.id}/preview?kind=translation"
                if j.job_type == JobType.NMT_TRANSLATE and j.output_data.get("segments"):
                    job_entry["translation_url"] = f"/jobs/{j.id}/preview?kind=translation"
            video_entry["jobs"].append(job_entry)
        processed_recent.append(video_entry)

    return {"active": active_items, "recent": processed_recent}


# ---------------------------------------------------------------------------
# Get single video
# ---------------------------------------------------------------------------

@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    client = MediaServiceClient()
    video_data = await client.get_video(video_id)
    if not video_data:
        raise HTTPException(status_code=404, detail="Video not found")
    if video_data["user_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this video")

    jobs_by_video, latest_task_by_video = await _fetch_job_enrichments(db, [video_id])
    await _enrich_video(video_data, client, jobs_by_video, latest_task_by_video)
    return video_data


# ---------------------------------------------------------------------------
# Delete video
# ---------------------------------------------------------------------------

@router.delete("/{video_id}", status_code=status.HTTP_200_OK)
async def delete_video(
    video_id: str,
    current_user: User = Depends(get_current_user),
):
    client = MediaServiceClient()
    video_data = await client.get_video(video_id)
    if not video_data:
        raise HTTPException(status_code=404, detail="Video not found")
    if video_data["user_id"] != current_user.user_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this video")

    deleted = await client.delete_video(video_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"message": "Video deleted successfully"}
