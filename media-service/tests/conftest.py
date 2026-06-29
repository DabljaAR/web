"""Shared pytest fixtures for media-service tests."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

_libs = Path(__file__).resolve().parents[2] / "libs" / "dablja-worker"
if str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

for _mod in ("aioboto3", "asyncpg"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
