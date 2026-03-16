import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from asyncssh import HostKeyNotVerifiable, PermissionDenied

from homeassistant.exceptions import ServiceValidationError

from ssh_command import async_setup, async_setup_entry
from ssh_command.const import CONF_ERROR, CONF_EXIT_STATUS, CONF_OUTPUT

SERVICE_DATA_BASE = {
    "host": "192.0.2.1",
    "username": "user",
    "password": "secret",
    "command": "echo hello",
    "check_known_hosts": False,
}


class _MockConnect:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        return None


class _MockConnectRaises:
    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *args):
        return None


class TestAsyncExecute(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_hass = MagicMock()
        self.mock_hass.data = {}

        async def _executor_job(func, *args):
            return func(*args)

        self.mock_hass.async_add_executor_job = AsyncMock(side_effect=_executor_job)
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"
        await async_setup_entry(self.mock_hass, mock_entry)
        await async_setup(self.mock_hass, {})
        self.handler = self.mock_hass.services.async_register.call_args[0][2]

    def _make_service_call(self, data):
        service_call = MagicMock()
        service_call.data = data
        return service_call

    def _make_mock_conn(self, stdout="", stderr="", exit_status=0):
        mock_result = MagicMock()
        mock_result.stdout = stdout
        mock_result.stderr = stderr
        mock_result.exit_status = exit_status
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)
        return mock_conn

    async def test_success(self):
        mock_conn = self._make_mock_conn(stdout="hello\n", stderr="", exit_status=0)
        service_call = self._make_service_call(SERVICE_DATA_BASE)

        with patch("ssh_command.coordinator.connect", return_value=_MockConnect(mock_conn)):
            with patch("ssh_command.coordinator.exists", return_value=False):
                result = await self.handler(service_call)

        self.assertEqual(result[CONF_OUTPUT], "hello\n")
        self.assertEqual(result[CONF_ERROR], "")
        self.assertEqual(result[CONF_EXIT_STATUS], 0)

    async def test_host_key_not_verifiable(self):
        service_call = self._make_service_call(SERVICE_DATA_BASE)

        with patch("ssh_command.coordinator.connect", return_value=_MockConnectRaises(HostKeyNotVerifiable("test"))):
            with patch("ssh_command.coordinator.exists", return_value=False):
                with self.assertRaises(ServiceValidationError) as ctx:
                    await self.handler(service_call)

        self.assertEqual(ctx.exception.translation_key, "host_key_not_verifiable")

    async def test_permission_denied(self):
        service_call = self._make_service_call(SERVICE_DATA_BASE)

        with patch("ssh_command.coordinator.connect", return_value=_MockConnectRaises(PermissionDenied("auth failed"))):
            with patch("ssh_command.coordinator.exists", return_value=False):
                with self.assertRaises(ServiceValidationError) as ctx:
                    await self.handler(service_call)

        self.assertEqual(ctx.exception.translation_key, "login_failed")

    async def test_timeout(self):
        service_call = self._make_service_call(SERVICE_DATA_BASE)

        with patch("ssh_command.coordinator.connect", return_value=_MockConnectRaises(TimeoutError())):
            with patch("ssh_command.coordinator.exists", return_value=False):
                with self.assertRaises(ServiceValidationError) as ctx:
                    await self.handler(service_call)

        self.assertEqual(ctx.exception.translation_key, "connection_timed_out")

    async def test_name_resolution_failure(self):
        err = OSError()
        err.strerror = "Temporary failure in name resolution"
        service_call = self._make_service_call(SERVICE_DATA_BASE)

        with patch("ssh_command.coordinator.connect", return_value=_MockConnectRaises(err)):
            with patch("ssh_command.coordinator.exists", return_value=False):
                with self.assertRaises(ServiceValidationError) as ctx:
                    await self.handler(service_call)

        self.assertEqual(ctx.exception.translation_key, "host_not_reachable")

    async def test_other_oserror_is_reraised(self):
        err = OSError("something else")
        err.strerror = "something else"
        service_call = self._make_service_call(SERVICE_DATA_BASE)

        with patch("ssh_command.coordinator.connect", return_value=_MockConnectRaises(err)):
            with patch("ssh_command.coordinator.exists", return_value=False):
                with self.assertRaises(OSError):
                    await self.handler(service_call)

    async def test_input_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
            tf.write("file content\n")
            tf_path = tf.name

        try:
            mock_conn = self._make_mock_conn(stdout="ok", stderr="", exit_status=0)
            data = {**SERVICE_DATA_BASE, "command": "cat", "input": tf_path}
            service_call = self._make_service_call(data)

            with patch("ssh_command.coordinator.connect", return_value=_MockConnect(mock_conn)):
                with patch("ssh_command.coordinator.exists", return_value=True):
                    await self.handler(service_call)

            call_kwargs = mock_conn.run.call_args[1]
            self.assertEqual(call_kwargs["input"], "file content\n")
        finally:
            os.unlink(tf_path)

    async def test_input_string_not_file(self):
        mock_conn = self._make_mock_conn(stdout="ok", stderr="", exit_status=0)
        data = {**SERVICE_DATA_BASE, "input": "inline input"}
        service_call = self._make_service_call(data)

        with patch("ssh_command.coordinator.connect", return_value=_MockConnect(mock_conn)):
            with patch("ssh_command.coordinator.exists", return_value=False):
                await self.handler(service_call)

        call_kwargs = mock_conn.run.call_args[1]
        self.assertEqual(call_kwargs["input"], "inline input")

    async def test_check_known_hosts_false(self):
        mock_conn = self._make_mock_conn()
        service_call = self._make_service_call(SERVICE_DATA_BASE)

        with patch("ssh_command.coordinator.connect", return_value=_MockConnect(mock_conn)) as mock_connect:
            with patch("ssh_command.coordinator.exists", return_value=False):
                await self.handler(service_call)

        call_kwargs = mock_connect.call_args[1]
        self.assertIsNone(call_kwargs["known_hosts"])

    async def test_known_hosts_file_exists(self):
        mock_conn = self._make_mock_conn()
        mock_known_hosts = MagicMock()
        data = {**SERVICE_DATA_BASE, "check_known_hosts": True, "known_hosts": "/home/user/.ssh/known_hosts"}
        service_call = self._make_service_call(data)

        with patch("ssh_command.coordinator.connect", return_value=_MockConnect(mock_conn)) as mock_connect:
            with patch("ssh_command.coordinator.exists", return_value=True):
                with patch("ssh_command.coordinator.read_known_hosts", return_value=mock_known_hosts) as mock_rkh:
                    await self.handler(service_call)

        mock_rkh.assert_called_once_with("/home/user/.ssh/known_hosts")
        call_kwargs = mock_connect.call_args[1]
        self.assertIs(call_kwargs["known_hosts"], mock_known_hosts)

    async def test_check_known_hosts_default_path_missing(self):
        mock_conn = self._make_mock_conn()
        data = {**SERVICE_DATA_BASE, "check_known_hosts": True}
        service_call = self._make_service_call(data)

        with patch("ssh_command.coordinator.connect", return_value=_MockConnect(mock_conn)) as mock_connect:
            with patch("ssh_command.coordinator.exists", return_value=False):
                await self.handler(service_call)

        call_kwargs = mock_connect.call_args[1]
        self.assertIsInstance(call_kwargs["known_hosts"], str)
