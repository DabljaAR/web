"""Tests for S3 client interop settings used by TTS uploads."""
from unittest.mock import MagicMock, patch

from dablja_worker.s3_client import make_s3_client, make_s3_client_config


def test_make_s3_client_config_disables_auto_checksums():
    config = make_s3_client_config()
    assert config.signature_version == "s3v4"
    assert config.s3 == {"addressing_style": "path"}
    assert config.request_checksum_calculation == "when_required"
    assert config.response_checksum_validation == "when_required"


@patch("dablja_worker.s3_client.boto3.client")
def test_make_s3_client_passes_interop_config(mock_client):
    make_s3_client(
        endpoint_url="https://storage.googleapis.com",
        aws_access_key_id="key",
        aws_secret_access_key="secret",
        region_name="auto",
    )
    mock_client.assert_called_once()
    _, kwargs = mock_client.call_args
    assert kwargs["endpoint_url"] == "https://storage.googleapis.com"
    assert kwargs["region_name"] == "auto"
    assert kwargs["config"].request_checksum_calculation == "when_required"


@patch("app.storage.make_s3_client")
def test_upload_wav_uses_shared_client(mock_make_client):
    import app.storage as storage_mod

    storage_mod._client = None
    from app.storage import upload_wav

    mock_s3 = MagicMock()
    mock_make_client.return_value = mock_s3

    key = upload_wav(b"RIFF", "tts/test.wav", bucket="media-bucket")

    assert key == "tts/test.wav"
    mock_s3.upload_fileobj.assert_called_once()
    args, kwargs = mock_s3.upload_fileobj.call_args
    assert args[1] == "media-bucket"
    assert args[2] == "tts/test.wav"
    assert kwargs["ExtraArgs"]["ContentType"] == "audio/wav"
