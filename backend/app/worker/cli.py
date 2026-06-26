"""CLI entry point for running RabbitMQ-native workers.

Usage::

    # Run a single worker
    python -m app.worker.run stt
    python -m app.worker.run nmt
    python -m app.worker.run tts
    python -m app.worker.run merge

    # With custom concurrency
    python -m app.worker.run stt --concurrency 1
"""
import argparse
import logging
import os
import sys

from app.config import settings


def _configure_device():
    """Configure CUDA/CPU device before any AI libraries load.
    Mirrors ``celery_app._configure_device()``."""
    silma_device = settings.SILMA_DEVICE.lower()
    if silma_device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        os.environ["TORCH_CUDA_ARCH_LIST"] = ""
        return "cpu"
    elif silma_device == "cuda":
        os.environ.pop("CUDA_VISIBLE_DEVICES", None)
        return "cuda"
    return "auto"


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main():
    parser = argparse.ArgumentParser(description="Run a RabbitMQ-native worker")
    parser.add_argument(
        "worker_type",
        choices=["stt", "nmt", "tts", "merge"],
        help="Which worker to start",
    )
    parser.add_argument(
        "--concurrency", type=int, default=None,
        help="Max concurrent messages (default: 1 for STT/TTS, 2 for NMT/Merge)",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        help="Logging level (default: INFO)",
    )
    parser.add_argument(
        "--rabbitmq-url", default=None,
        help="RabbitMQ URL (default: from settings.RABBITMQ_URL)",
    )

    args = parser.parse_args()
    setup_logging(args.log_level)

    # Configure device before any AI libraries load
    _configure_device()

    rmq_url = args.rabbitmq_url or getattr(settings, "RABBITMQ_URL", None)
    if not rmq_url:
        print("ERROR: RABBITMQ_URL not set. Set it via env var or --rabbitmq-url", file=sys.stderr)
        sys.exit(1)
        return

    concurrency_map = {"stt": 1, "nmt": 2, "tts": 1, "merge": 2}
    concurrency = args.concurrency or concurrency_map[args.worker_type]

    worker_map = {
        "stt": "app.worker.stt_worker",
        "nmt": "app.worker.nmt_worker",
        "tts": "app.worker.tts_worker",
        "merge": "app.worker.merge_worker",
    }

    module_name = worker_map[args.worker_type]
    import importlib
    try:
        mod = importlib.import_module(module_name)
    except ImportError as e:
        print(f"ERROR: Could not load worker module {module_name}: {e}", file=sys.stderr)
        sys.exit(1)
        return

    if not hasattr(mod, "create_worker"):
        print(f"ERROR: {module_name} has no create_worker() function", file=sys.stderr)
        sys.exit(1)
        return

    import asyncio

    worker = mod.create_worker(rmq_url, concurrency=concurrency)
    try:
        coro = worker.start()
        if asyncio.iscoroutine(coro):
            asyncio.run(coro)
    except KeyboardInterrupt:
        print("\nShutdown requested")


if __name__ == "__main__":
    main()
