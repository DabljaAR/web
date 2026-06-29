"""Shared fixtures for nmt-service unit tests.

All tests are pure unit tests: no real RabbitMQ, PostgreSQL, or NMT model needed.
Heavy dependencies are stubbed so pytest collects without them installed.
"""
import sys
from unittest.mock import MagicMock

# ── Stub heavy dependencies before any app import ────────────────────────────


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

sys.modules.setdefault("torch", MagicMock())
sys.modules.setdefault("transformers", MagicMock())
sys.modules.setdefault("sentencepiece", MagicMock())
sys.modules.setdefault("langdetect", MagicMock())
_botocore_stub = MagicMock()
_botocore_stub.config = MagicMock()
_botocore_stub.config.Config = MagicMock
_boto3_s3_transfer = MagicMock()
_boto3_s3_transfer.TransferConfig = MagicMock
_boto3_s3 = MagicMock()
_boto3_s3.transfer = _boto3_s3_transfer
_boto3_stub = MagicMock()
_boto3_stub.s3 = _boto3_s3
sys.modules.setdefault("boto3", _boto3_stub)
sys.modules.setdefault("boto3.s3", _boto3_s3)
sys.modules.setdefault("boto3.s3.transfer", _boto3_s3_transfer)
sys.modules.setdefault("botocore", _botocore_stub)
sys.modules.setdefault("botocore.config", _botocore_stub.config)
sys.modules.setdefault("groq", MagicMock())
