"""Integration tests for the SSH Command custom component.

These tests use ``pytest-homeassistant-custom-component`` which spins up a
real (in-process) Home Assistant instance per test.  No hand-rolled mocks
are needed for the HA side: the ``hass`` fixture IS a real ``HomeAssistant``
object, and services behave exactly as they do at runtime.

The SSH layer (asyncssh) is patched out so tests run without a real SSH server.

Run with:
    pytest tests/integration_tests/ -v
"""

from __future__ import annotations

import socket
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from asyncssh import HostKeyNotVerifiable, PermissionDenied

from custom_components.ssh_command.const import (
    CONF_CHECK_KNOWN_HOSTS,
    CONF_ERROR,
    CONF_EXIT_STATUS,
    CONF_INPUT,
    CONF_KEY_FILE,
    CONF_KNOWN_HOSTS,
    CONF_OUTPUT,
    DOMAIN,
    SERVICE_EXECUTE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(entry_id: str = "entry1") -> MockConfigEntry:
    """Return a MockConfigEntry for SSH Command."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        title="SSH Command",
        data={},
        version=1,
    )


async def _setup_entry(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Add *entry* to hass and wait for setup to complete."""
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


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


def _make_mock_conn(stdout="", stderr="", exit_status=0):
    """Return a mock SSH connection that returns the given result."""
    mock_result = MagicMock()
    mock_result.stdout = stdout
    mock_result.stderr = stderr
    mock_result.exit_status = exit_status
    mock_conn = AsyncMock()
    mock_conn.run = AsyncMock(return_value=mock_result)
    return mock_conn


# Service call data for a minimal valid execute request.
SERVICE_DATA_BASE = {
    "host": "192.0.2.1",
    "username": "user",
    "password": "secret",
    "command": "echo hello",
    "check_known_hosts": False,
}


# ---------------------------------------------------------------------------
# Entry setup
# ---------------------------------------------------------------------------


class TestSetupEntry:
    """Config entry setup creates the expected coordinator."""

    async def test_coordinator_stored_in_hass_data(self, hass: HomeAssistant) -> None:
        from custom_components.ssh_command.coordinator import SshCommandCoordinator

        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)

        coordinator = hass.data[DOMAIN]["e1"]
        assert isinstance(coordinator, SshCommandCoordinator)

    async def test_coordinator_holds_hass_reference(self, hass: HomeAssistant) -> None:
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)

        coordinator = hass.data[DOMAIN]["e1"]
        assert coordinator.hass is hass

    async def test_service_registered_after_setup(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        assert hass.services.has_service(DOMAIN, SERVICE_EXECUTE)

    async def test_multiple_entries_not_allowed(self, hass: HomeAssistant) -> None:
        """SSH Command is single-instance; a second flow attempt is aborted."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        await hass.async_block_till_done()
        assert result["type"] == "create_entry"

        result2 = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        await hass.async_block_till_done()
        assert result2["type"] == "abort"
        assert result2["reason"] == "single_instance_allowed"


# ---------------------------------------------------------------------------
# Entry unload
# ---------------------------------------------------------------------------


class TestUnloadEntry:
    """Unloading a config entry removes the coordinator from hass.data."""

    async def test_unload_removes_coordinator(self, hass: HomeAssistant) -> None:
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)
        assert "e1" in hass.data[DOMAIN]

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        assert "e1" not in hass.data.get(DOMAIN, {})

    async def test_unload_returns_true(self, hass: HomeAssistant) -> None:
        entry = _make_entry(entry_id="e1")
        await _setup_entry(hass, entry)

        result = await hass.config_entries.async_unload(entry.entry_id)
        assert result is True


# ---------------------------------------------------------------------------
# Config flow
# ---------------------------------------------------------------------------


class TestConfigFlow:
    """The config flow creates a single entry."""

    async def test_creates_entry_on_first_setup(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        await hass.async_block_till_done()

        assert result["type"] == "create_entry"
        assert result["title"] == "SSH Command"
        assert result["data"] == {}

    async def test_aborts_on_second_setup(self, hass: HomeAssistant) -> None:
        await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        await hass.async_block_till_done()

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        await hass.async_block_till_done()

        assert result["type"] == "abort"
        assert result["reason"] == "single_instance_allowed"


# ---------------------------------------------------------------------------
# Execute service — success cases
# ---------------------------------------------------------------------------


class TestExecuteServiceSuccess:
    """The execute service returns stdout/stderr/exit_status on success."""

    async def test_execute_returns_stdout(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        mock_conn = _make_mock_conn(stdout="hello\n", stderr="", exit_status=0)
        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnect(mock_conn)):
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                result = await hass.services.async_call(
                    DOMAIN,
                    SERVICE_EXECUTE,
                    SERVICE_DATA_BASE,
                    blocking=True,
                    return_response=True,
                )

        assert result[CONF_OUTPUT] == "hello\n"
        assert result[CONF_ERROR] == ""
        assert result[CONF_EXIT_STATUS] == 0

    async def test_execute_returns_stderr(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        mock_conn = _make_mock_conn(stdout="", stderr="some error", exit_status=1)
        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnect(mock_conn)):
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                result = await hass.services.async_call(
                    DOMAIN,
                    SERVICE_EXECUTE,
                    SERVICE_DATA_BASE,
                    blocking=True,
                    return_response=True,
                )

        assert result[CONF_ERROR] == "some error"
        assert result[CONF_EXIT_STATUS] == 1

    async def test_execute_with_password_auth(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        mock_conn = _make_mock_conn(stdout="ok")
        data = {**SERVICE_DATA_BASE, "password": "mysecret"}
        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnect(mock_conn)) as mock_connect:
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_EXECUTE,
                    data,
                    blocking=True,
                    return_response=True,
                )

        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["password"] == "mysecret"

    async def test_execute_with_key_file_auth(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        mock_conn = _make_mock_conn(stdout="ok")
        data = {
            "host": "192.0.2.1",
            "username": "user",
            "key_file": "/home/user/.ssh/id_rsa",
            "command": "echo hi",
            "check_known_hosts": False,
        }
        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnect(mock_conn)) as mock_connect:
            with patch("custom_components.ssh_command.coordinator.exists", return_value=True):
                with patch("custom_components.ssh_command.exists", return_value=True):
                    await hass.services.async_call(
                        DOMAIN,
                        SERVICE_EXECUTE,
                        data,
                        blocking=True,
                        return_response=True,
                    )

        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["client_keys"] == "/home/user/.ssh/id_rsa"

    async def test_execute_with_inline_input(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        mock_conn = _make_mock_conn(stdout="ok")
        data = {**SERVICE_DATA_BASE, "input": "inline input"}
        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnect(mock_conn)):
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_EXECUTE,
                    data,
                    blocking=True,
                    return_response=True,
                )

        call_kwargs = mock_conn.run.call_args[1]
        assert call_kwargs["input"] == "inline input"

    async def test_execute_with_input_file(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
            tf.write("file content\n")
            tf_path = tf.name

        try:
            mock_conn = _make_mock_conn(stdout="ok")
            data = {**SERVICE_DATA_BASE, "command": "cat", "input": tf_path}
            with patch("custom_components.ssh_command.coordinator.connect",
                       return_value=_MockConnect(mock_conn)):
                with patch("custom_components.ssh_command.coordinator.exists", return_value=True):
                    await hass.services.async_call(
                        DOMAIN,
                        SERVICE_EXECUTE,
                        data,
                        blocking=True,
                        return_response=True,
                    )

            call_kwargs = mock_conn.run.call_args[1]
            assert call_kwargs["input"] == "file content\n"
        finally:
            os.unlink(tf_path)

    async def test_execute_with_custom_timeout(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        mock_conn = _make_mock_conn()
        data = {**SERVICE_DATA_BASE, "timeout": 60}
        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnect(mock_conn)):
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_EXECUTE,
                    data,
                    blocking=True,
                    return_response=True,
                )

        call_kwargs = mock_conn.run.call_args[1]
        assert call_kwargs["timeout"] == 60


# ---------------------------------------------------------------------------
# Execute service — known hosts settings
# ---------------------------------------------------------------------------


class TestExecuteServiceKnownHosts:
    """Known hosts options are forwarded correctly to the SSH connection."""

    async def test_check_known_hosts_false_passes_none(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        mock_conn = _make_mock_conn()
        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnect(mock_conn)) as mock_connect:
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_EXECUTE,
                    SERVICE_DATA_BASE,  # has check_known_hosts: False
                    blocking=True,
                    return_response=True,
                )

        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["known_hosts"] is None

    async def test_check_known_hosts_true_with_custom_file(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        mock_conn = _make_mock_conn()
        mock_known_hosts = MagicMock()
        data = {
            **SERVICE_DATA_BASE,
            "check_known_hosts": True,
            "known_hosts": "/etc/ssh/known_hosts",
        }
        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnect(mock_conn)) as mock_connect:
            with patch("custom_components.ssh_command.coordinator.exists", return_value=True):
                with patch("custom_components.ssh_command.coordinator.read_known_hosts",
                           return_value=mock_known_hosts) as mock_rkh:
                    await hass.services.async_call(
                        DOMAIN,
                        SERVICE_EXECUTE,
                        data,
                        blocking=True,
                        return_response=True,
                    )

        mock_rkh.assert_called_once_with("/etc/ssh/known_hosts")
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["known_hosts"] is mock_known_hosts

    async def test_check_known_hosts_true_with_missing_file(self, hass: HomeAssistant) -> None:
        """If the known_hosts file does not exist the path is forwarded as-is."""
        entry = _make_entry()
        await _setup_entry(hass, entry)

        mock_conn = _make_mock_conn()
        data = {
            **SERVICE_DATA_BASE,
            "check_known_hosts": True,
            "known_hosts": "/nonexistent/known_hosts",
        }
        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnect(mock_conn)) as mock_connect:
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_EXECUTE,
                    data,
                    blocking=True,
                    return_response=True,
                )

        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["known_hosts"] == "/nonexistent/known_hosts"

    async def test_check_known_hosts_true_uses_default_path_when_missing(
        self, hass: HomeAssistant
    ) -> None:
        """Without a known_hosts path, the default ~/.ssh/known_hosts path is used."""
        entry = _make_entry()
        await _setup_entry(hass, entry)

        mock_conn = _make_mock_conn()
        data = {**SERVICE_DATA_BASE, "check_known_hosts": True}
        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnect(mock_conn)) as mock_connect:
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_EXECUTE,
                    data,
                    blocking=True,
                    return_response=True,
                )

        call_kwargs = mock_connect.call_args[1]
        known_hosts = call_kwargs["known_hosts"]
        assert isinstance(known_hosts, str)
        assert ".ssh" in known_hosts
        assert "known_hosts" in known_hosts


# ---------------------------------------------------------------------------
# Execute service — validation errors
# ---------------------------------------------------------------------------


class TestExecuteServiceValidation:
    """Validation errors prevent execution and surface helpful translation keys."""

    async def test_no_password_no_key_file_raises(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        with pytest.raises(ServiceValidationError) as exc_info:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_EXECUTE,
                {"host": "192.0.2.1", "username": "user", "command": "ls"},
                blocking=True,
                return_response=True,
            )

        assert exc_info.value.translation_key == "password_or_key_file_required"

    async def test_no_command_no_input_raises(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        with pytest.raises(ServiceValidationError) as exc_info:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_EXECUTE,
                {"host": "192.0.2.1", "username": "user", "password": "secret"},
                blocking=True,
                return_response=True,
            )

        assert exc_info.value.translation_key == "command_or_input"

    async def test_key_file_not_found_raises(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        with patch("custom_components.ssh_command.exists", return_value=False):
            with pytest.raises(ServiceValidationError) as exc_info:
                await hass.services.async_call(
                    DOMAIN,
                    SERVICE_EXECUTE,
                    {
                        "host": "192.0.2.1",
                        "username": "user",
                        "key_file": "/nonexistent/key",
                        "command": "ls",
                        "check_known_hosts": False,
                    },
                    blocking=True,
                    return_response=True,
                )

        assert exc_info.value.translation_key == "key_file_not_found"

    async def test_known_hosts_with_check_disabled_raises(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        with pytest.raises(ServiceValidationError) as exc_info:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_EXECUTE,
                {
                    "host": "192.0.2.1",
                    "username": "user",
                    "password": "secret",
                    "command": "ls",
                    "known_hosts": "/etc/ssh/known_hosts",
                    "check_known_hosts": False,
                },
                blocking=True,
                return_response=True,
            )

        assert exc_info.value.translation_key == "known_hosts_with_check_disabled"

    async def test_integration_not_set_up_raises(self, hass: HomeAssistant) -> None:
        """Without a config entry the coordinator is absent → service raises."""
        await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError) as exc_info:
            await hass.services.async_call(
                DOMAIN,
                SERVICE_EXECUTE,
                SERVICE_DATA_BASE,
                blocking=True,
                return_response=True,
            )

        assert exc_info.value.translation_key == "integration_not_set_up"


# ---------------------------------------------------------------------------
# Execute service — SSH error cases
# ---------------------------------------------------------------------------


class TestExecuteServiceErrors:
    """SSH error conditions surface as ServiceValidationError."""

    async def test_host_key_not_verifiable(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnectRaises(HostKeyNotVerifiable("test"))):
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                with pytest.raises(ServiceValidationError) as exc_info:
                    await hass.services.async_call(
                        DOMAIN,
                        SERVICE_EXECUTE,
                        SERVICE_DATA_BASE,
                        blocking=True,
                        return_response=True,
                    )

        assert exc_info.value.translation_key == "host_key_not_verifiable"

    async def test_permission_denied(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnectRaises(PermissionDenied("auth failed"))):
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                with pytest.raises(ServiceValidationError) as exc_info:
                    await hass.services.async_call(
                        DOMAIN,
                        SERVICE_EXECUTE,
                        SERVICE_DATA_BASE,
                        blocking=True,
                        return_response=True,
                    )

        assert exc_info.value.translation_key == "login_failed"

    async def test_timeout(self, hass: HomeAssistant) -> None:
        entry = _make_entry()
        await _setup_entry(hass, entry)

        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnectRaises(TimeoutError())):
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                with pytest.raises(ServiceValidationError) as exc_info:
                    await hass.services.async_call(
                        DOMAIN,
                        SERVICE_EXECUTE,
                        SERVICE_DATA_BASE,
                        blocking=True,
                        return_response=True,
                    )

        assert exc_info.value.translation_key == "connection_timed_out"

    async def test_host_not_reachable(self, hass: HomeAssistant) -> None:
        err = socket.gaierror("Name or service not known")
        entry = _make_entry()
        await _setup_entry(hass, entry)

        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnectRaises(err)):
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                with pytest.raises(ServiceValidationError) as exc_info:
                    await hass.services.async_call(
                        DOMAIN,
                        SERVICE_EXECUTE,
                        SERVICE_DATA_BASE,
                        blocking=True,
                        return_response=True,
                    )

        assert exc_info.value.translation_key == "host_not_reachable"

    async def test_other_oserror_is_reraised(self, hass: HomeAssistant) -> None:
        err = OSError("something else")
        entry = _make_entry()
        await _setup_entry(hass, entry)

        with patch("custom_components.ssh_command.coordinator.connect",
                   return_value=_MockConnectRaises(err)):
            with patch("custom_components.ssh_command.coordinator.exists", return_value=False):
                with pytest.raises(OSError):
                    await hass.services.async_call(
                        DOMAIN,
                        SERVICE_EXECUTE,
                        SERVICE_DATA_BASE,
                        blocking=True,
                        return_response=True,
                    )
