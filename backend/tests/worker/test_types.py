"""Unit tests for worker payload types (WorkerResultPayload, NewJobPayload)."""
import json

from app.worker.types import WorkerResultPayload, NewJobPayload


class TestWorkerResultPayload:
    def test_to_bytes_serializes_correctly(self):
        payload = WorkerResultPayload(
            job_id="job-001",
            job_type="STT_TRANSCRIBE",
            status="COMPLETED",
            output_data={"transcript": "hello", "segments": [{"start": 0.0}]},
            error="",
        )
        raw = payload.to_bytes()
        decoded = json.loads(raw)
        assert decoded["job_id"] == "job-001"
        assert decoded["job_type"] == "STT_TRANSCRIBE"
        assert decoded["status"] == "COMPLETED"
        assert decoded["output_data"]["transcript"] == "hello"
        assert decoded["error"] == ""

    def test_to_bytes_includes_error(self):
        payload = WorkerResultPayload(
            job_id="job-002",
            job_type="NMT_TRANSLATE",
            status="FAILED",
            output_data={},
            error="Translation model not loaded",
        )
        raw = payload.to_bytes()
        decoded = json.loads(raw)
        assert decoded["status"] == "FAILED"
        assert decoded["error"] == "Translation model not loaded"

    def test_to_bytes_empty_output_data(self):
        payload = WorkerResultPayload(
            job_id="job-003",
            job_type="TTS_SYNTHESIZE",
            status="COMPLETED",
        )
        raw = payload.to_bytes()
        decoded = json.loads(raw)
        assert decoded["output_data"] == {}

    def test_to_bytes_handles_numeric_values(self):
        payload = WorkerResultPayload(
            job_id="job-004",
            job_type="DUBBING_MERGE",
            status="COMPLETED",
            output_data={"progress": 100.0, "count": 42},
        )
        raw = payload.to_bytes()
        decoded = json.loads(raw)
        assert decoded["output_data"]["progress"] == 100.0
        assert decoded["output_data"]["count"] == 42

    def test_to_bytes_matches_go_struct_format(self):
        """Verify the JSON keys match the Go WorkerResultPayload struct exactly."""
        payload = WorkerResultPayload(
            job_id="test-id",
            job_type="STT_TRANSCRIBE",
            status="COMPLETED",
            output_data={"key": "val"},
            error="",
        )
        raw = payload.to_bytes()
        decoded = json.loads(raw)
        expected_keys = {"job_id", "job_type", "status", "output_data", "error"}
        assert set(decoded.keys()) == expected_keys


class TestNewJobPayload:
    def test_from_bytes_deserializes(self):
        data = json.dumps({"job_id": "job-001"}).encode("utf-8")
        payload = NewJobPayload.from_bytes(data)
        assert payload.job_id == "job-001"

    def test_from_bytes_round_trip(self):
        original = NewJobPayload(job_id="abc-123")
        raw = json.dumps({"job_id": original.job_id}).encode("utf-8")
        restored = NewJobPayload.from_bytes(raw)
        assert restored.job_id == original.job_id
