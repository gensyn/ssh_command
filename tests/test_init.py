"""Tests for the SSH Command integration (__init__.py)."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from asyncssh import HostKeyNotVerifiable, PermissionDenied

from homeassistant.exceptions import ServiceValidationError

from ssh_command import async_setup, async_setup_entry, async_unload_entry
from ssh_command.const import (
    CONF_EXIT_STATUS,
    CONF_ERROR,
    CONF_OUTPUT,
    DOMAIN,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SERVICE_DATA_BASE = {
    "host": "192.0.2.1",
    "username": "user",
    "password": "secret",
    "command": "echo hello",
    "check_known_hosts": False,
}


class _MockConnect:
    """Async context-manager that returns a mock SSH connection."""

    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        return None


class _MockConnectRaises:
    """Async context-manager that raises on entry."""

    def __init__(self, exc):
        self._exc = exc

    async def __aenter__(self):
        raise self._exc

    async def __aexit__(self, *args):
        return None


def _make_mock_conn(stdout="", stderr="", exit_status=0):
    mock_result = MagicMock()
    mock_result.stdout = stdout
    mock_result.stderr = stderr
    mock_result.exit_status = exit_status

    mock_conn = AsyncMock()
    mock_conn.run = AsyncMock(return_value=mock_result)
    return mock_conn


# ---------------------------------------------------------------------------
# _validate_service_data tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_no_password_no_key_file():
    """Raise when neither password nor key_file is provided."""
    from ssh_command import _validate_service_data

    with pytest.raises(ServiceValidationError) as exc_info:
        await _validate_service_data({"command": "echo hi"})
    assert exc_info.value.translation_key == "password_or_key_file_required"


@pytest.mark.asyncio
async def test_validate_no_command_no_input():
    """Raise when neither command nor input is provided."""
    from ssh_command import _validate_service_data

    with pytest.raises(ServiceValidationError) as exc_info:
        await _validate_service_data({"password": "secret"})
    assert exc_info.value.translation_key == "command_or_input"


@pytest.mark.asyncio
async def test_validate_key_file_not_found():
    """Raise when the key_file path does not exist on disk."""
    from ssh_command import _validate_service_data

    with patch("ssh_command.exists", return_value=False):
        with pytest.raises(ServiceValidationError) as exc_info:
            await _validate_service_data(
                {"key_file": "/nonexistent/key", "command": "ls"}
            )
    assert exc_info.value.translation_key == "key_file_not_found"


@pytest.mark.asyncio
async def test_validate_known_hosts_with_check_disabled():
    """Raise when known_hosts is set but check_known_hosts is False."""
    from ssh_command import _validate_service_data

    with patch("ssh_command.exists", return_value=True):
        with pytest.raises(ServiceValidationError) as exc_info:
            await _validate_service_data(
                {
                    "password": "secret",
                    "command": "ls",
                    "known_hosts": "/etc/ssh/known_hosts",
                    "check_known_hosts": False,
                }
            )
    assert exc_info.value.translation_key == "known_hosts_with_check_disabled"


@pytest.mark.asyncio
async def test_validate_valid_password_and_command():
    """No exception when password and command are both provided."""
    from ssh_command import _validate_service_data

    # Should not raise
    await _validate_service_data({"password": "secret", "command": "echo hi"})


@pytest.mark.asyncio
async def test_validate_valid_key_file_and_input():
    """No exception when an existing key_file and input are provided."""
    from ssh_command import _validate_service_data

    with patch("ssh_command.exists", return_value=True):
        await _validate_service_data(
            {"key_file": "/home/user/.ssh/id_rsa", "input": "some text"}
        )


@pytest.mark.asyncio
async def test_validate_valid_known_hosts_with_check_enabled():
    """No exception when known_hosts is set and check_known_hosts is True."""
    from ssh_command import _validate_service_data

    await _validate_service_data(
        {
            "password": "secret",
            "command": "ls",
            "known_hosts": "/etc/ssh/known_hosts",
            "check_known_hosts": True,
        }
    )


# ---------------------------------------------------------------------------
# async_setup / async_execute tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_setup_registers_service(hass):
    """async_setup registers the execute service and returns True."""
    result = await async_setup(hass, {})
    assert result is True
    assert hass.services.has_service(DOMAIN, "execute")


@pytest.mark.asyncio
async def test_execute_success(hass):
    """Service returns output, error and exit_status on success."""
    await async_setup(hass, {})

    mock_conn = _make_mock_conn(stdout="hello\n", stderr="", exit_status=0)
    with patch("ssh_command.connect", return_value=_MockConnect(mock_conn)):
        with patch("ssh_command.exists", return_value=False):
            result = await hass.services.async_call(
                DOMAIN,
                "execute",
                SERVICE_DATA_BASE,
                return_response=True,
                blocking=True,
            )

    assert result[CONF_OUTPUT] == "hello\n"
    assert result[CONF_ERROR] == ""
    assert result[CONF_EXIT_STATUS] == 0


@pytest.mark.asyncio
async def test_execute_host_key_not_verifiable(hass):
    """HostKeyNotVerifiable raises ServiceValidationError."""
    await async_setup(hass, {})

    with patch(
        "ssh_command.connect",
        return_value=_MockConnectRaises(HostKeyNotVerifiable("test")),
    ):
        with patch("ssh_command.exists", return_value=False):
            with pytest.raises(ServiceValidationError) as exc_info:
                await hass.services.async_call(
                    DOMAIN,
                    "execute",
                    SERVICE_DATA_BASE,
                    return_response=True,
                    blocking=True,
                )
    assert exc_info.value.translation_key == "host_key_not_verifiable"


@pytest.mark.asyncio
async def test_execute_permission_denied(hass):
    """PermissionDenied raises ServiceValidationError."""
    await async_setup(hass, {})

    with patch(
        "ssh_command.connect",
        return_value=_MockConnectRaises(PermissionDenied("auth failed")),
    ):
        with patch("ssh_command.exists", return_value=False):
            with pytest.raises(ServiceValidationError) as exc_info:
                await hass.services.async_call(
                    DOMAIN,
                    "execute",
                    SERVICE_DATA_BASE,
                    return_response=True,
                    blocking=True,
                )
    assert exc_info.value.translation_key == "login_failed"


@pytest.mark.asyncio
async def test_execute_timeout(hass):
    """TimeoutError raises ServiceValidationError."""
    await async_setup(hass, {})

    with patch(
        "ssh_command.connect",
        return_value=_MockConnectRaises(TimeoutError()),
    ):
        with patch("ssh_command.exists", return_value=False):
            with pytest.raises(ServiceValidationError) as exc_info:
                await hass.services.async_call(
                    DOMAIN,
                    "execute",
                    SERVICE_DATA_BASE,
                    return_response=True,
                    blocking=True,
                )
    assert exc_info.value.translation_key == "connection_timed_out"


@pytest.mark.asyncio
async def test_execute_name_resolution_failure(hass):
    """OSError with 'Temporary failure in name resolution' raises ServiceValidationError."""
    await async_setup(hass, {})

    err = OSError()
    err.strerror = "Temporary failure in name resolution"
    with patch(
        "ssh_command.connect",
        return_value=_MockConnectRaises(err),
    ):
        with patch("ssh_command.exists", return_value=False):
            with pytest.raises(ServiceValidationError) as exc_info:
                await hass.services.async_call(
                    DOMAIN,
                    "execute",
                    SERVICE_DATA_BASE,
                    return_response=True,
                    blocking=True,
                )
    assert exc_info.value.translation_key == "host_not_reachable"


@pytest.mark.asyncio
async def test_execute_other_oserror_is_reraised(hass):
    """An unrecognised OSError is re-raised as-is."""
    await async_setup(hass, {})

    err = OSError("something else")
    err.strerror = "something else"
    with patch(
        "ssh_command.connect",
        return_value=_MockConnectRaises(err),
    ):
        with patch("ssh_command.exists", return_value=False):
            with pytest.raises(OSError):
                await hass.services.async_call(
                    DOMAIN,
                    "execute",
                    SERVICE_DATA_BASE,
                    return_response=True,
                    blocking=True,
                )


@pytest.mark.asyncio
async def test_execute_input_from_file(hass):
    """When 'input' is a file path, its contents are sent as stdin."""
    await async_setup(hass, {})

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tf:
        tf.write("file content\n")
        tf_path = tf.name

    try:
        mock_conn = _make_mock_conn(stdout="ok", stderr="", exit_status=0)

        with patch("ssh_command.connect", return_value=_MockConnect(mock_conn)):
            with patch("ssh_command.exists", return_value=True):
                data = {**SERVICE_DATA_BASE, "input": tf_path}
                del data["command"]
                data["command"] = "cat"
                await hass.services.async_call(
                    DOMAIN,
                    "execute",
                    data,
                    return_response=True,
                    blocking=True,
                )

        # Verify that conn.run was called with the file content as input
        call_kwargs = mock_conn.run.call_args[1]
        assert call_kwargs["input"] == "file content\n"
    finally:
        os.unlink(tf_path)


@pytest.mark.asyncio
async def test_execute_input_string_not_file(hass):
    """When 'input' is a plain string (not a file path), it is used directly."""
    await async_setup(hass, {})

    mock_conn = _make_mock_conn(stdout="ok", stderr="", exit_status=0)

    with patch("ssh_command.connect", return_value=_MockConnect(mock_conn)):
        with patch("ssh_command.exists", return_value=False):
            data = {**SERVICE_DATA_BASE, "input": "inline input"}
            await hass.services.async_call(
                DOMAIN,
                "execute",
                data,
                return_response=True,
                blocking=True,
            )

    call_kwargs = mock_conn.run.call_args[1]
    assert call_kwargs["input"] == "inline input"


@pytest.mark.asyncio
async def test_execute_check_known_hosts_false(hass):
    """When check_known_hosts is False, known_hosts is set to None."""
    await async_setup(hass, {})

    mock_conn = _make_mock_conn()

    with patch("ssh_command.connect", return_value=_MockConnect(mock_conn)) as mock_connect:
        with patch("ssh_command.exists", return_value=False):
            await hass.services.async_call(
                DOMAIN,
                "execute",
                SERVICE_DATA_BASE,
                return_response=True,
                blocking=True,
            )

    call_kwargs = mock_connect.call_args[1]
    assert call_kwargs["known_hosts"] is None


@pytest.mark.asyncio
async def test_execute_known_hosts_file_exists(hass):
    """When known_hosts file exists, read_known_hosts is used to parse it."""
    await async_setup(hass, {})

    mock_conn = _make_mock_conn()
    mock_known_hosts = MagicMock()

    with patch("ssh_command.connect", return_value=_MockConnect(mock_conn)) as mock_connect:
        with patch("ssh_command.exists", return_value=True):
            with patch(
                "ssh_command.read_known_hosts", return_value=mock_known_hosts
            ) as mock_rkh:
                data = {
                    **SERVICE_DATA_BASE,
                    "check_known_hosts": True,
                    "known_hosts": "/home/user/.ssh/known_hosts",
                }
                await hass.services.async_call(
                    DOMAIN,
                    "execute",
                    data,
                    return_response=True,
                    blocking=True,
                )

    mock_rkh.assert_called_once_with("/home/user/.ssh/known_hosts")
    call_kwargs = mock_connect.call_args[1]
    assert call_kwargs["known_hosts"] is mock_known_hosts


@pytest.mark.asyncio
async def test_execute_check_known_hosts_default_path_missing(hass):
    """When check_known_hosts is True and no file exists, the path string is passed."""
    await async_setup(hass, {})

    mock_conn = _make_mock_conn()

    with patch("ssh_command.connect", return_value=_MockConnect(mock_conn)) as mock_connect:
        # exists() returns False → the raw path string is passed through
        with patch("ssh_command.exists", return_value=False):
            data = {**SERVICE_DATA_BASE, "check_known_hosts": True}
            await hass.services.async_call(
                DOMAIN,
                "execute",
                data,
                return_response=True,
                blocking=True,
            )

    call_kwargs = mock_connect.call_args[1]
    # The value should be a string (the path), not None
    assert isinstance(call_kwargs["known_hosts"], str)


# ---------------------------------------------------------------------------
# async_setup_entry / async_unload_entry tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_setup_entry_returns_true(hass):
    """async_setup_entry always returns True."""
    mock_entry = MagicMock()
    result = await async_setup_entry(hass, mock_entry)
    assert result is True


@pytest.mark.asyncio
async def test_async_unload_entry_returns_true(hass):
    """async_unload_entry always returns True."""
    mock_entry = MagicMock()
    result = await async_unload_entry(hass, mock_entry)
    assert result is True
