from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkerResultPayload:
    """Message body posted by AI workers to ``dablja.jobs.exchange`` with
    routing key ``job.results.*``.

    This must match the Go ``WorkerResultPayload`` struct in
    ``orchestrator/internal/pipeline/manager.go`` exactly.
    """
    job_id: str
    job_type: str
    status: str
    output_data: dict[str, Any] = field(default_factory=dict)
    error: str = ""

    def to_bytes(self) -> bytes:
        import json
        return json.dumps({
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "output_data": self.output_data,
            "error": self.error,
        }, default=str).encode("utf-8")


@dataclass
class NewJobPayload:
    """Message body from the Go orchestrator (or FastAPI) when a stage
    should start.

    Format: ``{"job_id": "..."}``
    """
    job_id: str

    @classmethod
    def from_bytes(cls, body: bytes) -> "NewJobPayload":
        import json
        data = json.loads(body)
        return cls(job_id=data["job_id"])
