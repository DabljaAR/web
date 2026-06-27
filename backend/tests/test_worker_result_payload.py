"""Golden fixture tests for WorkerResultPayload contract (shared with Go orchestrator)."""
import json
from pathlib import Path

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "orchestrator"
    / "internal"
    / "pipeline"
    / "testdata"
    / "worker_result_payload.json"
)


def _load_cases():
    with FIXTURE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def test_worker_result_payload_fixture_shape():
    """Each fixture case round-trips through JSON with expected fields."""
    for case in _load_cases():
        payload = case["input"]
        body = json.dumps(payload)
        parsed = json.loads(body)

        assert parsed.get("job_id", "") == case["expect_job_id"]
        assert parsed.get("status", "") == case["expect_status"]
        assert parsed.get("error", "") == case["expect_error"]

        # Contract fields the orchestrator and workers must agree on
        for key in ("job_id", "job_type", "status"):
            if key in payload:
                assert key in parsed

        if "output_data" in payload:
            assert isinstance(parsed.get("output_data"), dict)

        if "error" in payload:
            assert isinstance(parsed.get("error"), str)
