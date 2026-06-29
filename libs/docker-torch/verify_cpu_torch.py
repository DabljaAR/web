#!/usr/bin/env python3
"""Fail the build if torch is not a CPU-only wheel (guards against PyPI CUDA reinstall)."""
from __future__ import annotations

import os
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

    for pkg_name, env_var in (
        ("torchaudio", "TORCH_CPU_VERSION"),
        ("torchvision", "TORCHVISION_CPU_VERSION"),
    ):
        try:
            mod = __import__(pkg_name)
        except ImportError as exc:
            errors.append(f"{pkg_name} is not installed: {exc}")
            continue

        expected = os.environ.get(env_var, "").strip()
        if expected:
            version = getattr(mod, "__version__", "")
            if version and not version.startswith(expected):
                errors.append(
                    f"{pkg_name} {version!r} does not match expected {expected!r} "
                    f"(from {env_var})"
                )

    if errors:
        for msg in errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    import torchaudio
    import torchvision

    print(
        f"OK: torch {torch.__version__}, torchaudio {torchaudio.__version__}, "
        f"torchvision {torchvision.__version__} (cpu-only, cuda={torch.version.cuda})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
