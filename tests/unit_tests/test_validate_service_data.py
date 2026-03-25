import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from homeassistant.exceptions import ServiceValidationError

from ssh_command import _validate_service_data


class TestValidateServiceData(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_hass = MagicMock()

        async def _executor_job(func, *args):
            return func(*args)

        self.mock_hass.async_add_executor_job = AsyncMock(side_effect=_executor_job)

    async def test_no_password_no_key_file_raises(self):
        with self.assertRaises(ServiceValidationError) as ctx:
            await _validate_service_data(self.mock_hass, {"command": "echo hi"})
        self.assertEqual(ctx.exception.translation_key, "password_or_key_file_required")

    async def test_no_command_no_input_raises(self):
        with self.assertRaises(ServiceValidationError) as ctx:
            await _validate_service_data(self.mock_hass, {"password": "secret"})
        self.assertEqual(ctx.exception.translation_key, "command_or_input")

    async def test_key_file_not_found_raises(self):
        with patch("pathlib.Path.exists", return_value=False):
            with self.assertRaises(ServiceValidationError) as ctx:
                await _validate_service_data(self.mock_hass, {"key_file": "/nonexistent/key", "command": "ls"})
        self.assertEqual(ctx.exception.translation_key, "key_file_not_found")

    async def test_known_hosts_with_check_disabled_raises(self):
        with self.assertRaises(ServiceValidationError) as ctx:
            await _validate_service_data(self.mock_hass, {
                "password": "secret",
                "command": "ls",
                "known_hosts": "/etc/ssh/known_hosts",
                "check_known_hosts": False,
            })
        self.assertEqual(ctx.exception.translation_key, "known_hosts_with_check_disabled")

    async def test_valid_password_and_command(self):
        await _validate_service_data(self.mock_hass, {"password": "secret", "command": "echo hi"})

    async def test_valid_key_file_and_input(self):
        with patch("pathlib.Path.exists", return_value=True):
            await _validate_service_data(self.mock_hass, {"key_file": "/home/user/.ssh/id_rsa", "input": "some text"})

    async def test_valid_known_hosts_with_check_enabled(self):
        await _validate_service_data(self.mock_hass, {
            "password": "secret",
            "command": "ls",
            "known_hosts": "/etc/ssh/known_hosts",
            "check_known_hosts": True,
        })
