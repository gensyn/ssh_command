import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from asyncssh import HostKeyNotVerifiable, PermissionDenied

from homeassistant.exceptions import ServiceValidationError

from ssh_command.coordinator import SshCommandCoordinator
from ssh_command.const import CONF_OUTPUT, CONF_ERROR, CONF_EXIT_STATUS

EXECUTE_DATA_BASE = {
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


class TestSshCommandCoordinator(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_hass = MagicMock()

        async def _executor_job(func, *args):
            return func(*args)

        self.mock_hass.async_add_executor_job = AsyncMock(side_effect=_executor_job)
        self.coordinator = SshCommandCoordinator(self.mock_hass)

    def _make_mock_conn(self, stdout="", stderr="", exit_status=0):
        mock_result = MagicMock()
        mock_result.stdout = stdout
        mock_result.stderr = stderr
        mock_result.exit_status = exit_status
        mock_conn = AsyncMock()
        mock_conn.run = AsyncMock(return_value=mock_result)
        return mock_conn

    async def test_async_execute_success(self):
        mock_conn = self._make_mock_conn(stdout="hello\n", stderr="", exit_status=0)

        with patch("ssh_command.coordinator.connect", return_value=_MockConnect(mock_conn)):
            with patch("ssh_command.coordinator.exists", return_value=False):
                result = await self.coordinator.async_execute(EXECUTE_DATA_BASE)

        self.assertEqual(result[CONF_OUTPUT], "hello\n")
        self.assertEqual(result[CONF_ERROR], "")
        self.assertEqual(result[CONF_EXIT_STATUS], 0)

    async def test_async_execute_host_key_not_verifiable(self):
        with patch("ssh_command.coordinator.connect", return_value=_MockConnectRaises(HostKeyNotVerifiable("test"))):
            with patch("ssh_command.coordinator.exists", return_value=False):
                with self.assertRaises(ServiceValidationError) as ctx:
                    await self.coordinator.async_execute(EXECUTE_DATA_BASE)

        self.assertEqual(ctx.exception.translation_key, "host_key_not_verifiable")

    async def test_async_execute_permission_denied(self):
        with patch("ssh_command.coordinator.connect", return_value=_MockConnectRaises(PermissionDenied("auth failed"))):
            with patch("ssh_command.coordinator.exists", return_value=False):
                with self.assertRaises(ServiceValidationError) as ctx:
                    await self.coordinator.async_execute(EXECUTE_DATA_BASE)

        self.assertEqual(ctx.exception.translation_key, "login_failed")

    async def test_async_execute_timeout(self):
        with patch("ssh_command.coordinator.connect", return_value=_MockConnectRaises(TimeoutError())):
            with patch("ssh_command.coordinator.exists", return_value=False):
                with self.assertRaises(ServiceValidationError) as ctx:
                    await self.coordinator.async_execute(EXECUTE_DATA_BASE)

        self.assertEqual(ctx.exception.translation_key, "connection_timed_out")

    async def test_async_execute_name_resolution_failure(self):
        err = OSError()
        err.strerror = "Temporary failure in name resolution"

        with patch("ssh_command.coordinator.connect", return_value=_MockConnectRaises(err)):
            with patch("ssh_command.coordinator.exists", return_value=False):
                with self.assertRaises(ServiceValidationError) as ctx:
                    await self.coordinator.async_execute(EXECUTE_DATA_BASE)

        self.assertEqual(ctx.exception.translation_key, "host_not_reachable")

    async def test_async_execute_other_oserror_reraised(self):
        err = OSError("something else")
        err.strerror = "something else"

        with patch("ssh_command.coordinator.connect", return_value=_MockConnectRaises(err)):
            with patch("ssh_command.coordinator.exists", return_value=False):
                with self.assertRaises(OSError):
                    await self.coordinator.async_execute(EXECUTE_DATA_BASE)

    async def test_resolve_known_hosts_check_disabled(self):
        result = await self.coordinator._resolve_known_hosts(False, None)
        self.assertIsNone(result)

    async def test_resolve_known_hosts_file_exists(self):
        mock_known_hosts = MagicMock()

        with patch("ssh_command.coordinator.exists", return_value=True):
            with patch("ssh_command.coordinator.read_known_hosts", return_value=mock_known_hosts) as mock_rkh:
                result = await self.coordinator._resolve_known_hosts(True, "/home/user/.ssh/known_hosts")

        mock_rkh.assert_called_once_with("/home/user/.ssh/known_hosts")
        self.assertIs(result, mock_known_hosts)

    async def test_resolve_known_hosts_file_missing(self):
        with patch("ssh_command.coordinator.exists", return_value=False):
            result = await self.coordinator._resolve_known_hosts(True, "/nonexistent/known_hosts")

        self.assertEqual(result, "/nonexistent/known_hosts")

    async def test_resolve_known_hosts_default_path(self):
        with patch("ssh_command.coordinator.exists", return_value=False):
            result = await self.coordinator._resolve_known_hosts(True, None)

        self.assertIsInstance(result, str)
        self.assertIn(".ssh", result)
        self.assertIn("known_hosts", result)
