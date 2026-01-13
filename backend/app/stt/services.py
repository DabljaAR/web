"""
Service layer for STT business logic.
Location: sst/services.py
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import UploadFile
import uuid
import json
import os

from app.stt.models import WhisperModelManager
from app.stt.schema import TranscriptionResponse, TranscriptionSegment, TranscriptionMetadata

logger = logging.getLogger(__name__)

# In-memory job storage (replace with Redis/DB in production)
JOB_STORAGE: Dict[str, Dict[str, Any]] = {}
UPLOAD_DIR = Path("/tmp/transcriptions")


class TranscriptionService:
    """
    Service for handling transcription operations.
    Abstracts business logic from outes.
    """

    def __init__(self, model_manager: WhisperModelManager):
        """
        Initialize service with model manager.
        
        Args:
            model_manager: WhisperModelManager instance
        """
        self.model_manager = model_manager
        self._ensure_upload_dir()

    @staticmethod
    def _ensure_upload_dir() -> None:
        """Ensure upload directory exists."""
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    async def transcribe_file(
        self,
        file: UploadFile,
        language: Optional[str] = None
    ) -> TranscriptionResponse:
        """
        Transcribe an uploaded file synchronously.
        
        Args:
            file: Uploaded audio file
            language: Optional language code
            
        Returns:
            TranscriptionResponse with results
            
        Raises:
            FileNotFoundError: If file not found
            ValueError: If file invalid
            RuntimeError: If transcription fails
        """
        temp_path = None
        
        try:
            # Save uploaded file
            temp_path = self._save_upload(file)
            
            logger.info(f"📥 Processing file: {file.filename}")
            
            # Transcribe
            result = self.model_manager.transcribe(
                str(temp_path),
                language=language
            )
            
            # Convert to response model
            response = TranscriptionResponse(
                transcript=result["transcript"],
                segments=[
                    TranscriptionSegment(
                        start=seg["start"],
                        end=seg["end"],
                        text=seg["text"]
                    )
                    for seg in result["segments"]
                ],
                metadata=TranscriptionMetadata(
                    language=result["metadata"]["language"],
                    duration=result["metadata"]["duration"],
                    model_size=result["metadata"]["model_size"],
                    device=result["metadata"]["device"],
                    processing_time=result["metadata"]["processing_time"],
                    segment_count=result["metadata"]["segment_count"]
                )
            )
            
            logger.info(f"✅ Transcription complete: {file.filename}")
            return response
            
        finally:
            # Cleanup temp file
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file: {e}")

    async def submit_async_transcription(
        self,
        file: UploadFile,
        language: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Submit file for async transcription.
        
        Args:
            file: Uploaded audio file
            language: Optional language code
            
        Returns:
            Dict with task_id and status
        """
        task_id = str(uuid.uuid4())
        
        try:
            # Save file
            temp_path = self._save_upload(file)
            
            # Store job info
            JOB_STORAGE[task_id] = {
                "status": "queued",
                "filename": file.filename,
                "file_path": str(temp_path),
                "language": language,
                "result": None,
                "error": None
            }
            
            logger.info(f"📋 Async job queued: {task_id}")
            
            return {
                "task_id": task_id,
                "status": "queued",
                "message": f"Job submitted. Check status at /status/{task_id}"
            }
            
        except Exception as e:
            logger.error(f"Failed to queue async job: {e}")
            raise

    def get_job_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get status of an async transcription job.
        
        Args:
            task_id: Task ID to check
            
        Returns:
            Dict with job status and result (if ready)
            
        Raises:
            KeyError: If task not found
        """
        if task_id not in JOB_STORAGE:
            raise KeyError(f"Task not found: {task_id}")
        
        job = JOB_STORAGE[task_id]
        
        return {
            "task_id": task_id,
            "status": job["status"],
            "result": job["result"],
            "error": job["error"]
        }

    def process_async_transcription(self, task_id: str) -> None:
        """
        Process an async transcription job.
        Call this from a background task or worker.
        
        Args:
            task_id: Task to process
        """
        if task_id not in JOB_STORAGE:
            logger.error(f"Task not found: {task_id}")
            return
        
        job = JOB_STORAGE[task_id]
        file_path = job["file_path"]
        
        try:
            # Update status
            job["status"] = "processing"
            
            logger.info(f"⏳ Processing async job: {task_id}")
            
            # Transcribe
            result = self.model_manager.transcribe(
                file_path,
                language=job["language"]
            )
            
            # Store result
            job["result"] = {
                "transcript": result["transcript"],
                "segments": result["segments"],
                "metadata": result["metadata"]
            }
            job["status"] = "success"
            
            logger.info(f"✅ Async job complete: {task_id}")
            
        except Exception as e:
            logger.error(f"❌ Async job failed: {task_id} | {e}")
            job["status"] = "failed"
            job["error"] = str(e)
            
        finally:
            # Cleanup file
            try:
                Path(file_path).unlink()
            except:
                pass

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get API metrics.
        
        Returns:
            Dict with performance metrics
        """
        metrics = self.model_manager.get_metrics()
        
        # Add success rate
        total = metrics.get("total_requests", 0)
        successful = metrics.get("successful_transcriptions", 0)
        
        if total > 0:
            metrics["success_rate"] = (successful / total) * 100
        else:
            metrics["success_rate"] = 0.0
        
        return metrics

    def get_health(self) -> Dict[str, Any]:
        """
        Get health check info.
        
        Returns:
            Dict with health status
        """
        return {
            "status": "healthy",
            "model_loaded": True,
            "device": self.model_manager.device,
            "model_size": self.model_manager.model_size,
            "version": "1.0.0"
        }

    def cleanup(self) -> None:
        """Cleanup resources on shutdown."""
        self.model_manager.cleanup()
        logger.info("TranscriptionService cleanup completed")

    @staticmethod
    def _save_upload(file: UploadFile) -> Path:
        """
        Save uploaded file to temp directory.
        
        Args:
            file: UploadFile to save
            
        Returns:
            Path to saved file
        """
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        
        file_id = str(uuid.uuid4())
        temp_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
        
        # Read and save
        content = file.file.read()
        with open(temp_path, "wb") as f:
            f.write(content)
        
        logger.debug(f"Saved upload to: {temp_path}")
        
        return temp_path

    @staticmethod
    def cleanup_old_jobs(max_age_hours: int = 24) -> None:
        """
        Cleanup old job entries (not implemented in in-memory storage).
        Use with Redis/DB in production.
        
        Args:
            max_age_hours: Remove jobs older than this
        """
        # TODO: Implement with actual storage backend
        pass


class AsyncTranscriptionWorker:
    """
    Worker for processing async transcription jobs.
    Can be run in a separate process/thread.
    """

    def __init__(self, service: TranscriptionService):
        """
        Initialize worker.
        
        Args:
            service: TranscriptionService instance
        """
        self.service = service

    def process_queue(self, max_workers: int = 1) -> None:
        """
        Process queued jobs.
        
        Args:
            max_workers: Max concurrent workers (low traffic = 1)
        """
        import time
        
        processed = 0
        
        while True:
            # Find queued jobs
            queued_jobs = [
                task_id for task_id, job in JOB_STORAGE.items()
                if job["status"] == "queued"
            ]
            
            if not queued_jobs:
                # No jobs, sleep and retry
                time.sleep(5)
                continue
            
            # Process job
            task_id = queued_jobs[0]
            self.service.process_async_transcription(task_id)
            processed += 1
            
            logger.info(f"Processed {processed} jobs")

    def process_job(self, task_id: str) -> None:
        """
        Process a single job.
        
        Args:
            task_id: Task to process
        """
        self.service.process_async_transcription(task_id)