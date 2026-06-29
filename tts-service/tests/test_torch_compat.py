"""Tests for PyTorch compatibility shims used before SILMA import."""
import torch

from app.model import _patch_torch_xpu_compat


def test_patch_torch_xpu_compat_adds_stub_when_missing(monkeypatch):
    monkeypatch.delattr(torch, "xpu", raising=False)
    _patch_torch_xpu_compat()
    assert hasattr(torch, "xpu")
    assert torch.xpu.is_available() is False


def test_patch_torch_xpu_compat_is_idempotent():
    _patch_torch_xpu_compat()
    xpu = torch.xpu
    _patch_torch_xpu_compat()
    assert torch.xpu is xpu
