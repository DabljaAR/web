"""Shared fixtures for stt-service unit tests.

All tests are pure unit tests: no real RabbitMQ, PostgreSQL, MinIO,
or Whisper model is needed. Everything is stubbed at import time.
"""
import sys
from unittest.mock import MagicMock

# ── Stub all heavy dependencies before any app module can be imported ─────────
# These must be in place before the first `from app.xxx import` in a test.

class _FakeAMQPConnectionError(Exception):
    pass


class _FakeAMQPError(Exception):
    pass


_pika_stub = MagicMock()
_pika_stub.URLParameters = MagicMock
_pika_stub.BlockingConnection = MagicMock
_pika_stub.BasicProperties = MagicMock

_pika_exceptions = MagicMock()
_pika_exceptions.AMQPConnectionError = _FakeAMQPConnectionError
_pika_exceptions.AMQPError = _FakeAMQPError
_pika_stub.exceptions = _pika_exceptions

sys.modules.setdefault("pika", _pika_stub)
sys.modules.setdefault("pika.exceptions", _pika_exceptions)

sys.modules.setdefault("faster_whisper", MagicMock())
sys.modules.setdefault("torch", MagicMock())

_botocore_stub = MagicMock()
_botocore_config_stub = MagicMock()
_botocore_config_stub.Config = MagicMock
_botocore_stub.config = _botocore_config_stub
sys.modules.setdefault("boto3", MagicMock())
sys.modules.setdefault("botocore", _botocore_stub)
sys.modules.setdefault("botocore.config", _botocore_config_stub)
