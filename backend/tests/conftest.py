"""
Pytest configuration and fixtures.
Location: tests/conftest.py
"""

import pytest
import os
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

# CRITICAL: Add backend root to Python path so 'app' module can be imported
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

print(f"✓ Added to sys.path: {backend_root}")

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "True"


@pytest.fixture
def test_audio_file(tmp_path):
    """Create a temporary test audio file."""
    audio_file = tmp_path / "test_audio.mp3"
    audio_file.write_bytes(b"fake mp3 content")
    return audio_file


@pytest.fixture
def mock_whisper_model():
    """Mock WhisperModel."""
    mock_model = MagicMock()

    mock_segments = [
        MagicMock(start=0.0, end=2.5, text="Hello world"),
        MagicMock(start=2.5, end=5.0, text="This is a test"),
    ]

    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.duration = 5.0

    mock_model.transcribe.return_value = (iter(mock_segments), mock_info)

    return mock_model


@pytest.fixture
def settings():
    """Get test settings."""
    from app.config import settings
    return settings


@pytest.fixture
def app():
    """Create FastAPI test app."""
    from app.main import app
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_db_session():
    """Mock database session for core tests."""
    return AsyncMock()


@pytest.fixture
def mock_service():
    """Create mock transcription service."""  # <-- FIX: removed 'self'
    mock = MagicMock()
    mock.get_health.return_value = {
        "status": "healthy",
        "model_loaded": True,
        "device": "cpu",
        "version": "1.0.0"
    }
    mock.get_metrics.return_value = {
        "total_requests": 10,
        "successful_transcriptions": 9,
        "failed_transcriptions": 1,
        "avg_processing_time": 5.0,
        "device": "cpu",
        "model_size": "small",
        "is_transcribing": False,
        "success_rate": 90.0
    }
    return mock