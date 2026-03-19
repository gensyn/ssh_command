"""Playwright E2E tests: SSH command execution against real SSH test servers."""

from __future__ import annotations

import pytest
from typing import Any
import requests

from conftest import HA_URL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def execute(ha_api: requests.Session, payload: dict) -> requests.Response:
    """Call the ssh_command.execute service and return the raw response."""
    return ha_api.post(
        f"{HA_URL}/api/services/ssh_command/execute?return_response",
        json=payload,
    )


def base_payload(ssh_server: dict, command: str, **kwargs) -> dict:
    """Build a minimal execute payload from a server fixture and a command.

    Extra keyword arguments are merged into the payload, allowing callers to
    override any field (e.g. ``timeout``, ``check_known_hosts``).
    """
    payload = {
        "host": ssh_server["host"],
        "username": ssh_server["username"],
        "password": ssh_server["password"],
        "command": command,
        "check_known_hosts": False,
    }
    payload.update(kwargs)
    return payload


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCommandExecution:
    """End-to-end tests that execute real commands on the SSH test servers."""

    def test_echo_command(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """A simple echo command returns the expected string on stdout."""
        resp = execute(ha_api, base_payload(ssh_server_1, "echo hello"))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "hello" in data.get("output", "")
        assert data.get("exit_status") == 0

    def test_pwd_command(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """The pwd command returns a non-empty path."""
        resp = execute(ha_api, base_payload(ssh_server_1, "pwd"))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data.get("output", "").strip() != ""
        assert data.get("exit_status") == 0

    def test_command_stdout_captured(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Multiline output is fully captured."""
        resp = execute(ha_api, base_payload(ssh_server_1, "printf 'line1\\nline2\\nline3\\n'"))
        assert resp.status_code == 200, resp.text
        output = resp.json().get("output", "")
        assert "line1" in output
        assert "line2" in output
        assert "line3" in output

    def test_command_stderr_captured(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Output written to stderr is captured in the 'error' field."""
        resp = execute(ha_api, base_payload(ssh_server_1, "echo error_message >&2"))
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "error_message" in data.get("error", "")

    def test_nonzero_exit_status(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """A failing command returns a non-zero exit status."""
        resp = execute(ha_api, base_payload(ssh_server_1, "exit 42"))
        assert resp.status_code == 200, resp.text
        assert resp.json().get("exit_status") == 42

    def test_zero_exit_status(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """A successful command returns exit status 0."""
        resp = execute(ha_api, base_payload(ssh_server_1, "true"))
        assert resp.status_code == 200, resp.text
        assert resp.json().get("exit_status") == 0

    def test_command_with_env_variable(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Environment variable expansion works inside commands."""
        resp = execute(ha_api, base_payload(ssh_server_1, "echo $HOME"))
        assert resp.status_code == 200, resp.text
        assert resp.json().get("output", "").strip() != ""

    def test_second_ssh_server(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_2: dict) -> None:
        """Commands can be executed against the second SSH test server."""
        resp = execute(ha_api, base_payload(ssh_server_2, "echo server2"))
        assert resp.status_code == 200, resp.text
        assert "server2" in resp.json().get("output", "")

    def test_command_timeout_handling(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """A command that exceeds the timeout returns a 400 error."""
        payload = base_payload(ssh_server_1, "sleep 60")
        payload["timeout"] = 2
        resp = execute(ha_api, payload)
        # HA raises ServiceValidationError for timeout → HTTP 400
        assert resp.status_code == 400, resp.text

    def test_command_not_provided_requires_input(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Omitting both command and input returns a 400 validation error."""
        payload = {
            "host": ssh_server_1["host"],
            "username": ssh_server_1["username"],
            "password": ssh_server_1["password"],
            "check_known_hosts": False,
        }
        resp = execute(ha_api, payload)
        assert resp.status_code == 400, resp.text

    def test_no_password_or_key_returns_error(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Omitting both password and key_file returns a 400 validation error."""
        payload = {
            "host": ssh_server_1["host"],
            "username": ssh_server_1["username"],
            "command": "echo hi",
            "check_known_hosts": False,
        }
        resp = execute(ha_api, payload)
        assert resp.status_code == 400, resp.text

    def test_long_output_command(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """A command that produces a large amount of output is handled correctly."""
        resp = execute(ha_api, base_payload(ssh_server_1, "seq 1 500"))
        assert resp.status_code == 200, resp.text
        output = resp.json().get("output", "")
        assert "500" in output
