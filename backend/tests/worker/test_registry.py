"""Unit tests for the task registry."""
import pytest

from app.worker.registry import register, get_handler, list_handlers, get_routing_keys


class TestRegistry:
    def teardown_method(self):
        """Clean the registry after each test."""
        from app.worker.registry import _registry
        _registry.clear()

    def test_register_and_get_handler(self):
        @register(
            routing_key="job.start.stt",
            result_key="job.results.stt",
            job_type="STT_TRANSCRIBE",
            description="STT transcription",
        )
        async def my_handler(job_id: str) -> dict:
            return {"transcript": "hello"}

        handler = get_handler("job.start.stt")
        assert handler is not None
        assert handler.routing_key == "job.start.stt"
        assert handler.result_key == "job.results.stt"
        assert handler.job_type == "STT_TRANSCRIBE"
        assert handler.description == "STT transcription"
        assert handler.fn is my_handler

    def test_register_rejects_sync_function(self):
        with pytest.raises(TypeError, match="must be an async function"):

            @register(
                routing_key="job.start.nmt",
                result_key="job.results.nmt",
                job_type="NMT_TRANSLATE",
            )
            def sync_handler(job_id: str) -> dict:
                return {}

    def test_get_handler_returns_none_for_missing(self):
        assert get_handler("job.start.nonexistent") is None

    def test_list_handlers_returns_all(self):
        @register(
            routing_key="job.start.a",
            result_key="job.results.a",
            job_type="TYPE_A",
        )
        async def handler_a(job_id: str) -> dict:
            return {}

        @register(
            routing_key="job.start.b",
            result_key="job.results.b",
            job_type="TYPE_B",
        )
        async def handler_b(job_id: str) -> dict:
            return {}

        handlers = list_handlers()
        assert len(handlers) == 2
        routing_keys = {h.routing_key for h in handlers}
        assert routing_keys == {"job.start.a", "job.start.b"}

    def test_get_routing_keys(self):
        @register(
            routing_key="job.start.merge",
            result_key="job.results.merge",
            job_type="DUBBING_MERGE",
        )
        async def merge_handler(job_id: str) -> dict:
            return {}

        keys = get_routing_keys()
        assert "job.start.merge" in keys
