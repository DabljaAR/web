"""Unit tests for SILMA TTS wrapper behavior."""

from unittest.mock import patch


class _DummySilmaModel:
    def __init__(self, fail_first_tashkeel=False):
        self.fail_first_tashkeel = fail_first_tashkeel
        self.calls = []

    def infer(self, **kwargs):
        self.calls.append(dict(kwargs))
        if self.fail_first_tashkeel and kwargs.get("force_tashkeel"):
            self.fail_first_tashkeel = False
            raise AttributeError("'NoneType' object has no attribute 'do_tashkeel'")

        with open(kwargs["file_wave"], "wb") as out:
            out.write(b"fake-wav")

        return None, 24000, None


class TestSilmaTtsModelManager:
    def test_synthesize_passes_force_tashkeel_to_infer(self, tmp_path):
        """infer() should receive the configured force_tashkeel value explicitly."""
        from app.config import settings
        from app.tts.models import SilmaTTSModelManager

        ref_audio = tmp_path / "ref.wav"
        ref_audio.write_bytes(b"ref")

        dummy_model = _DummySilmaModel()
        manager = SilmaTTSModelManager()

        with patch.object(manager, "_load_model", return_value=dummy_model), patch.object(
            manager, "_ensure_short_reference_audio", return_value=str(ref_audio)
        ), patch.object(settings, "TTS_FORCE_TASHKEEL", False):
            audio = manager.synthesize(text="مرحبا", ref_audio_path=str(ref_audio))

        assert audio == b"fake-wav"
        assert dummy_model.calls
        assert dummy_model.calls[0]["force_tashkeel"] is False

    def test_synthesize_retries_without_tashkeel_on_known_error(self, tmp_path):
        """When SILMA raises do_tashkeel NoneType error, retry once with force_tashkeel=False."""
        from app.config import settings
        from app.tts.models import SilmaTTSModelManager

        ref_audio = tmp_path / "ref.wav"
        ref_audio.write_bytes(b"ref")

        dummy_model = _DummySilmaModel(fail_first_tashkeel=True)
        manager = SilmaTTSModelManager()

        with patch.object(manager, "_load_model", return_value=dummy_model), patch.object(
            manager, "_ensure_short_reference_audio", return_value=str(ref_audio)
        ), patch.object(settings, "TTS_FORCE_TASHKEEL", True):
            audio = manager.synthesize(text="مرحبا", ref_audio_path=str(ref_audio))

        assert audio == b"fake-wav"
        assert len(dummy_model.calls) == 2
        assert dummy_model.calls[0]["force_tashkeel"] is True
        assert dummy_model.calls[1]["force_tashkeel"] is False
