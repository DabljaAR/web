"""
Unit tests for configuration module.
Location: tests/test_config.py
"""

import os
import pytest
from app.config import Settings


class TestSettings:
    """Test Settings class."""
    
    def test_database_url_from_env(self):
        """Test DATABASE_URL loads from environment."""
        test_url = "postgresql://user:pass@localhost/testdb"
        os.environ["DATABASE_URL"] = test_url
        
        settings = Settings()
        assert settings.DATABASE_URL == test_url
    
    def test_database_url_default(self):
        """Test DATABASE_URL default value."""
        if "DATABASE_URL" in os.environ:
            del os.environ["DATABASE_URL"]
        
        settings = Settings()
        assert "postgresql" in settings.DATABASE_URL or "localhost" in settings.DATABASE_URL
    
    def test_secret_key_from_env(self):
        """Test SECRET_KEY loads from environment."""
        test_key = "test-secret-key-12345"
        os.environ["SECRET_KEY"] = test_key
        
        settings = Settings()
        assert settings.SECRET_KEY == test_key
    
    def test_authentication_settings(self):
        """Test authentication settings."""
        settings = Settings()
        assert settings.ALGORITHM == "HS256"
        assert settings.ACCESS_TOKEN_EXPIRE_MINUTES > 0
        assert settings.REFRESH_TOKEN_EXPIRE_DAYS > 0
    
    def test_log_level_from_env(self):
        """Test LOG_LEVEL loads from environment."""
        os.environ["LOG_LEVEL"] = "DEBUG"
        
        settings = Settings()
        assert settings.LOG_LEVEL == "DEBUG"
    
    def test_log_settings_defaults(self):
        """Test logging settings have proper defaults."""
        settings = Settings()
        
        assert settings.LOG_DIR == "logs"
        assert settings.LOG_FILE == "app.log"
        assert settings.LOG_MAX_BYTES > 0
        assert settings.LOG_BACKUP_COUNT > 0
        assert isinstance(settings.LOG_ENABLE_CONSOLE, bool)
        assert isinstance(settings.LOG_ENABLE_FILE, bool)
    
    def test_stt_model_size_default(self):
        """Test STT_MODEL_SIZE default value."""
        if "STT_MODEL_SIZE" in os.environ:
            del os.environ["STT_MODEL_SIZE"]
        
        settings = Settings()
        assert settings.STT_MODEL_SIZE == "small"
    
    def test_stt_model_size_from_env(self):
        """Test STT_MODEL_SIZE loads from environment."""
        os.environ["STT_MODEL_SIZE"] = "medium"
        
        settings = Settings()
        assert settings.STT_MODEL_SIZE == "medium"
    
    def test_stt_device_auto_detection(self):
        """Test STT_DEVICE auto-detection."""
        os.environ["STT_DEVICE"] = "auto"
        
        settings = Settings()
        device = settings.get_device()
        
        # Device should be either cuda or cpu
        assert device in ["cuda", "cpu"]
    
    def test_stt_device_explicit(self):
        """Test STT_DEVICE explicit value."""
        os.environ["STT_DEVICE"] = "cpu"
        
        settings = Settings()
        assert settings.get_device() == "cpu"
    
    def test_stt_compute_type_auto(self):
        """Test STT_COMPUTE_TYPE auto-selection."""
        os.environ["STT_COMPUTE_TYPE"] = "auto"
        
        settings = Settings()
        compute_type = settings.get_compute_type()
        
        # Compute type should be valid
        valid_types = ["float32", "float16", "int8", "int8_float32", "int8_float16"]
        assert compute_type in valid_types
    
    def test_stt_compute_type_explicit(self):
        """Test STT_COMPUTE_TYPE explicit value."""
        os.environ["STT_COMPUTE_TYPE"] = "int8"
        
        settings = Settings()
        assert settings.get_compute_type() == "int8"
    
    def test_stt_max_audio_duration(self):
        """Test STT_MAX_AUDIO_DURATION setting."""
        os.environ["STT_MAX_AUDIO_DURATION"] = "7200"
        
        settings = Settings()
        assert settings.STT_MAX_AUDIO_DURATION == 7200
    
    def test_stt_max_file_size_gb(self):
        """Test STT_MAX_FILE_SIZE_GB setting."""
        os.environ["STT_MAX_FILE_SIZE_GB"] = "10"
        
        settings = Settings()
        assert settings.STT_MAX_FILE_SIZE_GB == 10.0
    
    def test_stt_retry_settings(self):
        """Test STT retry settings."""
        settings = Settings()
        
        assert settings.STT_RETRY_ATTEMPTS >= 1
        assert settings.STT_RETRY_DELAY >= 0
    
    def test_server_settings(self):
        """Test server settings."""
        settings = Settings()
        
        assert settings.HOST in ["0.0.0.0", "localhost", "127.0.0.1"]
        assert settings.PORT > 0
        assert settings.WORKERS >= 1
    
    def test_cors_origins(self):
        """Test CORS_ORIGINS is set."""
        settings = Settings()
        
        assert isinstance(settings.CORS_ORIGINS, list)
        assert len(settings.CORS_ORIGINS) > 0
        assert any("localhost" in origin for origin in settings.CORS_ORIGINS)
    
    def test_environment_settings(self):
        """Test ENVIRONMENT and DEBUG settings."""
        os.environ["ENVIRONMENT"] = "production"
        os.environ["DEBUG"] = "False"
        
        settings = Settings()
        
        assert settings.ENVIRONMENT == "production"
        assert settings.DEBUG is False
    
    def test_is_production_property(self):
        """Test is_production property."""
        os.environ["ENVIRONMENT"] = "production"
        settings = Settings()
        
        assert settings.is_production is True
        assert settings.is_development is False
    
    def test_is_development_property(self):
        """Test is_development property."""
        os.environ["ENVIRONMENT"] = "development"
        settings = Settings()
        
        assert settings.is_development is True
        assert settings.is_production is False
    
    def test_get_device_cuda_availability(self):
        """Test get_device handles CUDA availability."""
        settings = Settings()
        
        # Should not raise exception regardless of CUDA availability
        device = settings.get_device()
        assert device is not None
    
    def test_compute_type_matches_device(self):
        """Test compute type selection matches device."""
        os.environ["STT_DEVICE"] = "cpu"
        os.environ["STT_COMPUTE_TYPE"] = "auto"
        
        settings = Settings()
        compute_type = settings.get_compute_type()
        
        # CPU should get int8
        assert compute_type == "int8"