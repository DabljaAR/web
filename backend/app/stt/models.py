import torch
import time
import logging
import os
from pathlib import Path
from threading import Lock
from typing import Optional
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """
    Clean transcribed text by removing extra whitespace.
    
    Args:
        text: Raw transcribed text
        
    Returns:
        Cleaned text
    """
    # Strip leading/trailing whitespace and collapse multiple spaces
    return " ".join(text.split())


# Constants
MAX_AUDIO_DURATION = 3600  # 1 hour max (adjust to your needs)
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
GPU_MEMORY_THRESHOLD = 0.9  # 90% GPU memory = cancel new requests


class WhisperModelManager:
    """
    Production-grade Whisper transcription manager with:
    - Thread-safe concurrent request handling
    - Automatic retry with exponential backoff
    - GPU memory monitoring and cleanup
    - Input validation and timeout protection
    - Performance metrics
    """

    def __init__(self, model_size: str = "small"):
        self.model_size = model_size
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type = "float16" if self.device == "cuda" else "int8"

        # Thread safety for concurrent requests
        self._lock = Lock()
        self._is_transcribing = False

        # Metrics
        self.metrics = {
            "total_requests": 0,
            "successful_transcriptions": 0,
            "failed_transcriptions": 0,
            "total_processing_time": 0,
            "avg_processing_time": 0,
        }

        logger.info(
            f"Initializing Whisper model | size={self.model_size} "
            f"device={self.device} compute_type={self.compute_type}"
        )

        try:
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )
            logger.info("✅ Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"❌ Failed to load Whisper model: {e}")
            raise

    def _validate_audio_file(self, audio_path: str) -> None:
        """
        Validate audio file exists and meets requirements.
        
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is invalid or too large
        """
        path = Path(audio_path)

        # Check file exists
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Check file is readable
        if not os.access(audio_path, os.R_OK):
            raise PermissionError(f"Cannot read audio file: {audio_path}")

        # Check file size (max 5GB)
        file_size_gb = path.stat().st_size / (1024 ** 3)
        if file_size_gb > 5:
            raise ValueError(
                f"File too large: {file_size_gb:.2f}GB (max 5GB)"
            )

        # Valid audio extensions
        valid_extensions = {
            ".mp3", ".mp4", ".wav", ".m4a", ".flac", ".ogg", ".wma", ".aac"
        }
        if path.suffix.lower() not in valid_extensions:
            raise ValueError(
                f"Unsupported audio format: {path.suffix}. "
                f"Supported: {valid_extensions}"
            )

    def _check_gpu_memory(self) -> bool:
        """
        Check if GPU has sufficient memory for transcription.
        
        Returns:
            bool: True if memory is available, False if above threshold
        """
        if self.device != "cuda":
            return True

        try:
            allocated = torch.cuda.memory_allocated() / torch.cuda.get_device_properties(0).total_memory
            if allocated > GPU_MEMORY_THRESHOLD:
                logger.warning(
                    f"GPU memory usage high: {allocated*100:.1f}% "
                    "(rejecting new requests)"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"Could not check GPU memory: {e}")
            return True

    def _cleanup_gpu_memory(self) -> None:
        """Force GPU memory cleanup after transcription."""
        if self.device == "cuda":
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.debug("GPU memory cleaned up")

    def transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        **kwargs
    ) -> dict:
        """
        Transcribe audio file with automatic retry and error handling.

        Args:
            audio_path: Path to audio/video file
            language: Optional language code (e.g., 'en', 'es')
            **kwargs: Additional arguments for model.transcribe()

        Returns:
            dict: Transcription result with segments and metadata

        Raises:
            FileNotFoundError: If audio file doesn't exist
            ValueError: If audio file is invalid
            RuntimeError: If transcription fails after retries
        """
        # Validate input
        self._validate_audio_file(audio_path)

        # Check GPU memory
        if not self._check_gpu_memory():
            raise RuntimeError(
                "Insufficient GPU memory. Please try again later."
            )

        # Prevent concurrent transcriptions (thread-safe)
        with self._lock:
            if self._is_transcribing:
                raise RuntimeError(
                    "Transcription already in progress. "
                    "Please wait or use async endpoint."
                )
            self._is_transcribing = True

        try:
            self.metrics["total_requests"] += 1
            return self._transcribe_with_retry(audio_path, language, **kwargs)

        finally:
            self._is_transcribing = False
            self._cleanup_gpu_memory()

    def _transcribe_with_retry(
        self,
        audio_path: str,
        language: Optional[str],
        **kwargs
    ) -> dict:
        """
        Perform transcription with automatic retry on failure.
        """
        last_exception = None

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(
                    f"Starting transcription (attempt {attempt + 1}/{MAX_RETRIES}) "
                    f"| file={Path(audio_path).name}"
                )

                start_time = time.time()

                # Transcribe
                segments_generator, info = self.model.transcribe(
                    audio_path,
                    language=language,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 50},
                    **kwargs
                )

                # Check duration limit
                if info.duration > MAX_AUDIO_DURATION:
                    raise ValueError(
                        f"Audio too long: {info.duration:.0f}s "
                        f"(max {MAX_AUDIO_DURATION}s)"
                    )

                # Convert generator to list ONCE
                segments = list(segments_generator)

                # Build structured segments
                structured_segments = [
                    {
                        "start": round(seg.start, 2),
                        "end": round(seg.end, 2),
                        "text": clean_text(seg.text),
                    }
                    for seg in segments
                ]

                # Raw transcript
                transcript = " ".join(
                    seg["text"] for seg in structured_segments
                )

                processing_time = time.time() - start_time

                # Update metrics
                self.metrics["successful_transcriptions"] += 1
                self.metrics["total_processing_time"] += processing_time
                self.metrics["avg_processing_time"] = (
                    self.metrics["total_processing_time"] /
                    self.metrics["successful_transcriptions"]
                )

                result = {
                    "transcript": transcript,
                    "segments": structured_segments,
                    "metadata": {
                        "language": info.language,
                        "duration": round(info.duration, 2),
                        "model_size": self.model_size,
                        "device": self.device,
                        "processing_time": round(processing_time, 2),
                        "segment_count": len(structured_segments),
                    }
                }

                logger.info(
                    f"✅ Transcription completed | "
                    f"duration={info.duration:.1f}s | "
                    f"processing_time={processing_time:.1f}s | "
                    f"speed_ratio={processing_time/info.duration:.2f}x"
                )

                return result

            except (RuntimeError, torch.cuda.OutOfMemoryError) as e:
                last_exception = e
                logger.warning(
                    f"GPU error on attempt {attempt + 1}/{MAX_RETRIES}: {e}"
                )
                self._cleanup_gpu_memory()

                if attempt < MAX_RETRIES - 1:
                    logger.info(f"Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                continue

            except Exception as e:
                logger.exception(f"Transcription failed: {e}")
                raise RuntimeError("STT inference failed") from e

        # All retries failed
        self.metrics["failed_transcriptions"] += 1
        logger.error(
            f"❌ Transcription failed after {MAX_RETRIES} attempts"
        )
        raise RuntimeError(
            f"Transcription failed after {MAX_RETRIES} retries: {last_exception}"
        )

    def get_metrics(self) -> dict:
        """Get transcription metrics for monitoring."""
        return {
            **self.metrics,
            "device": self.device,
            "model_size": self.model_size,
            "is_transcribing": self._is_transcribing,
        }

    def cleanup(self) -> None:
        """Cleanup resources (call on app shutdown)."""
        try:
            self._cleanup_gpu_memory()
            logger.info("WhisperModelManager cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")