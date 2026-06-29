#!/usr/bin/env python3
"""Fail the build if ONNX Runtime is not a CPU-only install (guards against onnxruntime-gpu)."""
from __future__ import annotations

import importlib.metadata
import sys


def main() -> int:
    errors: list[str] = []

    try:
        importlib.metadata.version("onnxruntime-gpu")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        errors.append(
            "onnxruntime-gpu is installed — CPU images must use onnxruntime only"
        )

    try:
        import onnxruntime as ort
    except ImportError as exc:
        errors.append(f"onnxruntime is not installed: {exc}")
        for msg in errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    providers = ort.get_available_providers()
    if "CPUExecutionProvider" not in providers:
        errors.append(
            f"CPUExecutionProvider missing from providers={providers!r}"
        )

    if errors:
        for msg in errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    print(f"OK: onnxruntime {ort.__version__} (cpu-only, providers={providers})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
