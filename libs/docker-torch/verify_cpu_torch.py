#!/usr/bin/env python3
"""Fail the build if torch is not a CPU-only wheel (guards against PyPI CUDA reinstall)."""
from __future__ import annotations

import sys


def main() -> int:
    try:
        import torch
    except ImportError as exc:
        print(f"ERROR: torch is not installed: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    if torch.version.cuda is not None:
        errors.append(
            f"torch.version.cuda={torch.version.cuda!r} — expected None for CPU-only builds"
        )

    if torch.cuda.is_available():
        errors.append(
            "torch.cuda.is_available() is True — CPU images must not expose CUDA"
        )

    # PyPI CUDA wheels often ship NVIDIA libs under site-packages/nvidia/
    try:
        import nvidia  # type: ignore[import-not-found]
    except ImportError:
        pass
    else:
        errors.append(
            "nvidia.* packages are present — likely a CUDA torch wheel from PyPI"
        )

    if errors:
        for msg in errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    print(f"OK: torch {torch.__version__} (cpu-only, cuda={torch.version.cuda})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
