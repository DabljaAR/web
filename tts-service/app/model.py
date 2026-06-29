"""SILMA-TTS model manager (non-Celery, for microservice use).

Lazy-loads the SILMA model on first inference and keeps it in memory.
Patches torchaudio and catt_tashkeel to ensure runtime paths are writable.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

import soundfile as sf
import torch

from app.config import settings

logger = logging.getLogger(__name__)


class _TorchXPUStub:
    """Minimal torch.xpu stand-in for PyTorch builds without Intel XPU support."""

    @staticmethod
    def is_available() -> bool:
        return False


def _patch_torch_xpu_compat() -> None:
    """silma-tts probes torch.xpu at import time; CPU torch 2.2 lacks that namespace."""
    if hasattr(torch, "xpu"):
        return
    torch.xpu = _TorchXPUStub()  # type: ignore[attr-defined]
    logger.info("Patched torch.xpu stub for PyTorch builds without XPU support")


class TTSModelManager:
    """Owns the SILMA-TTS model lifecycle for the microservice process."""

    def __init__(self):
        self._model: Optional[object] = None
        self._device: Optional[str] = None

    @property
    def device(self) -> str:
        if self._device is None:
            silma_device = settings.SILMA_DEVICE.lower()
            if silma_device == "cpu":
                self._device = "cpu"
            elif silma_device == "cuda":
                self._device = "cuda"
            else:
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info("SILMA-TTS device: %s (SILMA_DEVICE=%s)", self._device, silma_device)
        return self._device

    # ── model loading ────────────────────────────────────────────────────────

    def load_model(self):
        if self._model is not None:
            logger.info("[TTS][CACHE] model already loaded in memory")
            return self._model

        self._configure_runtime_paths()
        self._patch_catt_tashkeel_model_dir()
        self._patch_torchaudio_load()
        _patch_torch_xpu_compat()

        from silma_tts.api import SilmaTTS

        if settings.HF_TOKEN:
            os.environ["HF_TOKEN"] = settings.HF_TOKEN
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

        logger.info("Loading SILMA-TTS model...")
        load_started = time.time()
        try:
            self._model = SilmaTTS(
                hf_cache_dir=settings.HF_HOME,
                enable_normalizer=settings.TTS_ENABLE_NORMALIZER,
                force_tashkeel=settings.TTS_FORCE_TASHKEEL,
            )
        except Exception as e:
            raise RuntimeError(
                f"SILMA-TTS init failed: uid={os.getuid()} "
                f"hf_home={os.environ.get('HF_HOME')}. {e}"
            ) from e

        logger.info(
            "[TTS][CACHE] model loaded in %.1fs",
            time.time() - load_started,
        )
        return self._model

    def _configure_runtime_paths(self) -> None:
        preferred_root = Path("/model-cache")
        fallback_root = Path(tempfile.gettempdir()) / "dabljaar" / "model-cache"
        writable_root = (
            preferred_root if self._is_writable_dir(preferred_root) else fallback_root
        )
        writable_root.mkdir(parents=True, exist_ok=True)

        defaults = {
            "HF_HOME": str(writable_root / "hf"),
            "HUGGINGFACE_HUB_CACHE": str(writable_root / "hf" / "hub"),
            "TRANSFORMERS_CACHE": str(writable_root / "hf" / "transformers"),
            "XDG_CACHE_HOME": str(writable_root / "xdg-cache"),
            "TORCH_HOME": str(writable_root / "torch"),
            "CATT_TASHKEEL_MODEL_DIR": str(writable_root / "catt_tashkeel" / "onnx_models"),
        }
        for env_name, default_path in defaults.items():
            resolved = os.environ.get(env_name, "").strip() or default_path
            os.environ[env_name] = resolved
            Path(resolved).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _is_writable_dir(path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def _patch_catt_tashkeel_model_dir(self) -> None:
        try:
            import urllib.request
            import zipfile

            import catt_tashkeel.models as catt_models
        except Exception:
            return

        base_cls = getattr(catt_models, "BaseONNXTashkeel", None)
        if base_cls is None or getattr(base_cls, "_dabljaar_patch_applied", False):
            return

        configured = settings.catt_tashkeel_dir()
        model_root = Path(os.environ.get("CATT_TASHKEEL_MODEL_DIR", "") or configured)
        model_root.mkdir(parents=True, exist_ok=True)
        os.environ["CATT_TASHKEEL_MODEL_DIR"] = str(model_root)

        def _download_models(self, model_type):
            downloads = {
                "ed_model": "https://github.com/abjadai/catt/releases/download/v2/ed_model_onnx.zip",
                "eo_model": "https://github.com/abjadai/catt/releases/download/v2/eo_model_onnx.zip",
            }
            if model_type not in downloads:
                raise ValueError(f"Unknown model type: {model_type}")
            extract_dir = model_root / model_type
            if (extract_dir / "encoder.onnx").exists() and (extract_dir / "decoder.onnx").exists():
                return
            extract_dir.mkdir(parents=True, exist_ok=True)
            zip_path = model_root / f"{model_type}.zip"
            try:
                urllib.request.urlretrieve(downloads[model_type], zip_path)
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    zip_ref.extractall(extract_dir)
            finally:
                zip_path.unlink(missing_ok=True)

        def _get_model_paths(self, encoder_path, decoder_path, model_type):
            if encoder_path is None or decoder_path is None:
                target_dir = model_root / model_type
                if not (target_dir / "encoder.onnx").exists():
                    self._download_models(model_type)
                encoder_path = encoder_path or str(target_dir / "encoder.onnx")
                decoder_path = decoder_path or str(target_dir / "decoder.onnx")
            return encoder_path, decoder_path

        setattr(base_cls, "_download_models", _download_models)
        setattr(base_cls, "_get_model_paths", _get_model_paths)
        setattr(base_cls, "_dabljaar_patch_applied", True)
        logger.info("Patched catt_tashkeel ONNX model dir to %s", model_root)

    def _patch_torchaudio_load(self) -> None:
        try:
            import torchaudio
        except Exception:
            return
        if getattr(torchaudio, "_dabljaar_patched", False):
            return

        def _sf_load(
            path,
            frame_offset: int = 0,
            num_frames: int = -1,
            normalize: bool = True,
            channels_first: bool = True,
            format=None,
            buffer_size: int = 65536,
            backend=None,
        ):
            del format, buffer_size, backend
            data, sample_rate = sf.read(
                str(path),
                start=max(frame_offset, 0),
                frames=num_frames if num_frames and num_frames > 0 else -1,
                dtype="float32",
                always_2d=True,
            )
            waveform = torch.from_numpy(data.T.copy())
            if not channels_first:
                waveform = waveform.T
            if not normalize and waveform.dtype.is_floating_point:
                waveform = (waveform * 32768.0).to(torch.int16)
            return waveform, sample_rate

        torchaudio.load = _sf_load
        torchaudio._dabljaar_patched = True
        logger.info("Patched torchaudio.load → soundfile backend")

    # ── reference audio resolution ───────────────────────────────────────────

    def resolve_reference_audio(self) -> str:
        """Return a local path to the SILMA reference audio WAV."""
        if settings.SILMA_REFERENCE_AUDIO and os.path.exists(settings.SILMA_REFERENCE_AUDIO):
            return settings.SILMA_REFERENCE_AUDIO
        try:
            import importlib.util
            spec = importlib.util.find_spec("silma_tts")
            if spec:
                locs = spec.submodule_search_locations if spec.submodule_search_locations else []
                pkg_root = locs[0] if locs else (os.path.dirname(spec.origin) if spec.origin else None)
                if pkg_root:
                    bundled = os.path.join(pkg_root, "infer", "ref_audio_samples", "ar.ref.24k.wav")
                    if os.path.exists(bundled):
                        return bundled
        except Exception:
            pass
        return ""

    def _ensure_short_reference_audio(self, ref_audio_path: str, *, max_seconds: float = 8.0) -> str:
        src = Path(ref_audio_path)
        if not src.exists():
            return ref_audio_path

        stat = src.stat()
        cache_key = f"{src.resolve()}|{stat.st_mtime_ns}|{stat.st_size}|{max_seconds}".encode("utf-8")
        digest = hashlib.sha256(cache_key).hexdigest()[:16]

        cache_dir = Path(tempfile.gettempdir()) / "dabljaar" / "tts_ref_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        out_path = cache_dir / f"ref_{digest}_{int(max_seconds * 1000)}ms.wav"
        if out_path.exists() and out_path.stat().st_size > 0:
            return str(out_path)

        tmp_out = out_path.with_name(out_path.name + ".tmp.wav")
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src), "-f", "wav", "-t", str(max_seconds),
            "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(tmp_out),
        ]
        try:
            subprocess.run(cmd, check=True)
            tmp_out.replace(out_path)
            return str(out_path)
        except FileNotFoundError:
            logger.warning("ffmpeg not found; using original reference audio: %s", src)
            return ref_audio_path
        except subprocess.CalledProcessError as e:
            logger.warning("Failed to prepare short reference clip: %s; using original", e)
            return ref_audio_path

    # ── synthesis ────────────────────────────────────────────────────────────

    def synthesize(
        self,
        text: str,
        *,
        ref_audio_path: Optional[str] = None,
        ref_text: Optional[str] = None,
        nfe_step: Optional[int] = None,
        speed: Optional[float] = None,
        cfg_strength: Optional[float] = None,
        sway_sampling_coef: Optional[float] = None,
        target_rms: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> bytes:
        model = self.load_model()

        _ref_audio = ref_audio_path or self.resolve_reference_audio()
        _ref_text = ref_text if ref_text is not None else settings.SILMA_REFERENCE_TEXT
        if not isinstance(_ref_text, str):
            _ref_text = ""
        if not _ref_text.strip():
            _ref_text = None

        if not _ref_audio:
            raise ValueError("Reference audio is required (set SILMA_REFERENCE_AUDIO)")
        if not os.path.exists(_ref_audio):
            raise FileNotFoundError(f"Reference audio not found: {_ref_audio}")

        _ref_audio = self._ensure_short_reference_audio(_ref_audio, max_seconds=8.0)

        clean_text = text.replace('"', "").strip()
        if not clean_text:
            raise ValueError("TTS synthesis received empty text")

        _nfe = nfe_step if nfe_step is not None else settings.TTS_DEFAULT_NFE_STEP
        _speed = speed if speed is not None else settings.TTS_DEFAULT_SPEED
        _cfg = cfg_strength if cfg_strength is not None else settings.TTS_DEFAULT_CFG_STRENGTH
        _sway = sway_sampling_coef if sway_sampling_coef is not None else settings.TTS_DEFAULT_SWAY_COEF
        _rms = target_rms if target_rms is not None else settings.TTS_DEFAULT_TARGET_RMS

        logger.info(
            "[TTS] synthesize | nfe=%d speed=%.2f cfg=%.2f sway=%.2f rms=%.2f chars=%d",
            _nfe, _speed, _cfg, _sway, _rms, len(clean_text),
        )

        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            infer_kwargs = {
                "ref_file": _ref_audio,
                "ref_text": _ref_text,
                "gen_text": clean_text,
                "file_wave": tmp_path,
                "seed": seed,
                "speed": _speed,
                "cfg_strength": _cfg,
                "nfe_step": _nfe,
                "sway_sampling_coef": _sway,
                "target_rms": _rms,
                "force_tashkeel": settings.TTS_FORCE_TASHKEEL,
            }
            try:
                model.infer(**infer_kwargs)
            except AttributeError as exc:
                if "do_tashkeel" in str(exc) and infer_kwargs["force_tashkeel"]:
                    logger.warning("[TTS] tashkeel init error; retrying with force_tashkeel=False")
                    infer_kwargs["force_tashkeel"] = False
                    model.infer(**infer_kwargs)
                else:
                    raise

            with open(tmp_path, "rb") as f:
                audio_bytes = f.read()

            logger.info("[TTS] synthesis done | bytes=%d", len(audio_bytes))
            return audio_bytes
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


_tts = TTSModelManager()
