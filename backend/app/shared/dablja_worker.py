"""Compatibility shim — re-exports from the canonical dablja_worker package.

The source of truth is libs/dablja-worker/dablja_worker/.
This file exists so backend code (tts_bridge.py etc.) continues to import
from app.shared.dablja_worker without changes until Phase 2 removes the bridge.

Phase 2: delete this file once tts_bridge.py is removed.
"""
from dablja_worker.consumer import (  # noqa: F401
    consume_loop,
    make_engine,
    classify_failure,
    check_cancelled,
)
