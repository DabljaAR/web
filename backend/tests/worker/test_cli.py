"""Unit tests for the worker CLI entry point."""
import sys
from unittest.mock import MagicMock, patch

import pytest


class TestCliArgumentParsing:
    def test_main_with_valid_worker_type(self):
        """Parsing valid worker types should succeed."""
        from app.worker.cli import main

        test_args = ["prog", "stt"]
        with patch.object(sys, "argv", test_args), \
             patch("app.worker.cli._configure_device", return_value="cpu"), \
             patch("app.worker.cli.settings") as mock_settings, \
             patch("importlib.import_module") as mock_import:
            mock_settings.RABBITMQ_URL = "amqp://localhost/"
            mock_mod = MagicMock()
            mock_mod.create_worker.return_value = MagicMock()
            mock_import.return_value = mock_mod

            main()

        mock_import.assert_called_once_with("app.worker.stt_worker")

    def test_main_exits_on_missing_rabbitmq_url(self):
        from app.worker.cli import main

        test_args = ["prog", "stt"]
        with patch.object(sys, "argv", test_args), \
             patch("app.worker.cli.settings") as mock_settings, \
             patch.object(sys, "exit") as mock_exit:
            setattr(mock_settings, "RABBITMQ_URL", None)

            main()

        mock_exit.assert_called_once_with(1)

    def test_main_exits_on_bad_worker_module(self):
        from app.worker.cli import main

        test_args = ["prog", "stt"]
        with patch.object(sys, "argv", test_args), \
             patch("app.worker.cli._configure_device", return_value="cpu"), \
             patch("app.worker.cli.settings") as mock_settings, \
             patch("importlib.import_module", side_effect=ImportError("no module")), \
             patch.object(sys, "exit") as mock_exit:
            mock_settings.RABBITMQ_URL = "amqp://localhost/"

            main()

        mock_exit.assert_called_once_with(1)

    def test_main_exits_when_module_has_no_create_worker(self):
        from app.worker.cli import main

        test_args = ["prog", "stt"]
        with patch.object(sys, "argv", test_args), \
             patch("app.worker.cli._configure_device", return_value="cpu"), \
             patch("app.worker.cli.settings") as mock_settings, \
             patch("importlib.import_module") as mock_import, \
             patch.object(sys, "exit") as mock_exit:
            mock_settings.RABBITMQ_URL = "amqp://localhost/"
            mock_mod = MagicMock(spec=[])  # no create_worker
            mock_import.return_value = mock_mod

            main()

        mock_exit.assert_called_once_with(1)

    def test_main_uses_custom_concurrency(self):
        from app.worker.cli import main

        test_args = ["prog", "nmt", "--concurrency", "5"]
        with patch.object(sys, "argv", test_args), \
             patch("app.worker.cli._configure_device", return_value="cpu"), \
             patch("app.worker.cli.settings") as mock_settings, \
             patch("importlib.import_module") as mock_import:
            mock_settings.RABBITMQ_URL = "amqp://localhost/"
            mock_mod = MagicMock()
            mock_worker = MagicMock()
            mock_mod.create_worker.return_value = mock_worker
            mock_import.return_value = mock_mod

            main()

        mock_mod.create_worker.assert_called_once_with(
            "amqp://localhost/", concurrency=5
        )

    def test_configure_device_sets_env_cpu(self):
        with patch("app.worker.cli.settings") as mock_settings:
            mock_settings.SILMA_DEVICE = "cpu"
            from app.worker.cli import _configure_device
            import os

            result = _configure_device()
            assert result == "cpu"
            assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""

    def test_configure_device_clears_env_cuda(self):
        import os
        os.environ["CUDA_VISIBLE_DEVICES"] = "0"

        with patch("app.worker.cli.settings") as mock_settings:
            mock_settings.SILMA_DEVICE = "cuda"
            from app.worker.cli import _configure_device

            result = _configure_device()
            assert result == "cuda"
            assert "CUDA_VISIBLE_DEVICES" not in os.environ
