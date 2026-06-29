"""Shared pytest fixtures for tts-service tests."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Allow importing libs/dablja-worker without pip install (CI still pip installs).
_libs = Path(__file__).resolve().parents[2] / "libs" / "dablja-worker"
if str(_libs) not in sys.path:
    sys.path.insert(0, str(_libs))

# Stub heavy deps before worker/model import (CI installs minimal deps only).
for _mod in ("soundfile", "torch", "silma_tts"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
