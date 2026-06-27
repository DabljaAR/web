"""Task registry — a lightweight decorator-based system for registering
message handlers with RabbitMQ routing keys.

Usage::

    from app.worker.registry import register

    @register(
        routing_key="job.start.stt",
        result_key="job.results.stt",
        job_type="STT_TRANSCRIBE",
        description="Speech-to-text transcription",
    )
    async def handle_stt(job_id: str) -> dict:
        ...
        return {"transcript": "...", "segments": [...]}
"""
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Optional


@dataclass
class TaskHandler:
    """Metadata for a registered task handler."""
    routing_key: str
    result_key: str
    job_type: str
    description: str
    fn: Callable[..., Coroutine[Any, Any, dict]]


_registry: dict[str, TaskHandler] = {}


def register(
    routing_key: str,
    result_key: str,
    job_type: str,
    description: str = "",
) -> Callable:
    """Decorator that registers an async function as a task handler.

    Args:
        routing_key: RabbitMQ routing key to consume from (e.g. ``job.start.stt``).
        result_key: RabbitMQ routing key to publish results to (e.g. ``job.results.stt``).
        job_type: The ``JobType`` string value (e.g. ``STT_TRANSCRIBE``).
        description: Human-readable description of the task.
    """
    def decorator(fn: Callable) -> Callable:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"{fn.__name__} must be an async function")
        handler = TaskHandler(
            routing_key=routing_key,
            result_key=result_key,
            job_type=job_type,
            description=description or fn.__doc__ or "",
            fn=fn,
        )
        _registry[routing_key] = handler
        return fn
    return decorator


def get_handler(routing_key: str) -> Optional[TaskHandler]:
    """Look up a registered handler by routing key."""
    return _registry.get(routing_key)


def list_handlers() -> list[TaskHandler]:
    """Return all registered handlers."""
    return list(_registry.values())


def get_routing_keys() -> list[str]:
    """Return all registered routing keys."""
    return list(_registry.keys())
