import logging
import os
import threading
from typing import List, Optional

import numpy as np
import torch

from app.config import settings

logger = logging.getLogger(__name__)

HF_ENV_VARS = {
    "HF_HOME": settings.HF_HOME,
    "HF_HUB_CACHE": os.path.join(settings.HF_HOME, "hub"),
    "TRANSFORMERS_CACHE": os.path.join(settings.HF_HOME, "transformers"),
    "HUGGINGFACE_HUB_CACHE": os.path.join(settings.HF_HOME, "hub"),
}
for k, v in HF_ENV_VARS.items():
    os.environ.setdefault(k, v)
if settings.HF_TOKEN:
    os.environ.setdefault("HF_TOKEN", settings.HF_TOKEN)


class OmniVoiceManager:
    _model = None
    _lock = threading.Lock()
    _device: Optional[str] = None
    _model_name: Optional[str] = None

    @classmethod
    def get_model(cls):
        if cls._model is None:
            with cls._lock:
                if cls._model is None:
                    from omnivoice import OmniVoice

                    device = cls._resolve_device()
                    dtype = cls._resolve_dtype()
                    logger.info(
                        "Loading OmniVoice model | name=%s device=%s dtype=%s",
                        settings.OMNIVOICE_MODEL_NAME,
                        device,
                        dtype,
                    )
                    model = OmniVoice.from_pretrained(
                        settings.OMNIVOICE_MODEL_NAME,
                        device_map=device,
                        dtype=dtype,
                    )
                    cls._model = model
                    cls._device = device
                    cls._model_name = settings.OMNIVOICE_MODEL_NAME
                    logger.info("OmniVoice model loaded successfully")
        return cls._model

    @classmethod
    def is_loaded(cls) -> bool:
        return cls._model is not None

    @classmethod
    def device(cls) -> Optional[str]:
        return cls._device

    @classmethod
    def model_name(cls) -> Optional[str]:
        return cls._model_name

    @staticmethod
    def _resolve_device() -> str:
        dev = settings.OMNIVOICE_DEVICE
        if dev == "auto":
            if torch.cuda.is_available():
                return "cuda:0"
            return "cpu"
        return dev

    @staticmethod
    def _resolve_dtype():
        if settings.OMNIVOICE_DTYPE == "float16":
            return torch.float16
        return torch.float32

    @classmethod
    def synthesize(
        cls,
        text: str,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        instruct: Optional[str] = None,
    ) -> List[np.ndarray]:
        model = cls.get_model()
        kwargs = {"text": text}

        if ref_audio:
            kwargs["ref_audio"] = ref_audio
            if ref_text:
                kwargs["ref_text"] = ref_text
        elif instruct:
            kwargs["instruct"] = instruct

        kwargs["num_step"] = settings.OMNIVOICE_NUM_STEP
        kwargs["guidance_scale"] = settings.OMNIVOICE_GUIDANCE_SCALE
        kwargs["speed"] = settings.OMNIVOICE_SPEED

        return model.generate(**kwargs)
