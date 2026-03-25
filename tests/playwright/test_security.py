"""Playwright E2E tests: SSH Command security properties."""

from __future__ import annotations

import pytest
from typing import Any
import requests

from conftest import HA_URL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def execute(ha_api: requests.Session, payload: dict) -> requests.Response:
    """Call the ssh_command.execute service."""
    return ha_api.post(
        f"{HA_URL}/api/services/ssh_command/execute?return_response",
        json=payload,
    )


def svc_data(resp: requests.Response) -> dict:
    """Extract the ssh_command service response dict from an HA API response."""
    return resp.json().get("service_response", resp.json())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSecurity:
    """Tests that validate the security properties of the SSH Command integration."""

    def test_invalid_password_rejected(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """An incorrect password results in a 400 authentication error."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": "definitely_wrong_password",
                "command": "echo hi",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 400, resp.text

    def test_invalid_username_rejected(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """An incorrect username results in a 400 authentication error."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": "nonexistent_user_xyz",
                "password": ssh_server_1["password"],
                "command": "echo hi",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 400, resp.text

    def test_unreachable_host_rejected(self, ha_api: requests.Session, ensure_integration: Any) -> None:
        """Connecting to an unreachable host results in a 400 connection error."""
        resp = execute(
            ha_api,
            {
                "host": "192.0.2.255",  # RFC 5737 TEST-NET – documentation address, typically unreachable
                "username": "user",
                "password": "pass",
                "command": "echo hi",
                "check_known_hosts": False,
                "timeout": 5,
            },
        )
        assert resp.status_code == 400, resp.text

    def test_nonexistent_host_rejected(self, ha_api: requests.Session, ensure_integration: Any) -> None:
        """Connecting to a non-existent hostname results in a 400 DNS error."""
        resp = execute(
            ha_api,
            {
                "host": "this.host.does.not.exist.invalid",  # .invalid TLD is guaranteed non-resolvable (RFC 2606)
                "username": "user",
                "password": "pass",
                "command": "echo hi",
                "check_known_hosts": False,
                "timeout": 5,
            },
        )
        assert resp.status_code == 400, resp.text

    def test_nonexistent_key_file_rejected(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Referencing a key file that does not exist results in a validation error."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "key_file": "/nonexistent/path/id_rsa",
                "command": "echo hi",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 400, resp.text

    def test_api_requires_authentication(self) -> None:
        """Calling the HA service API without an auth token is rejected with 401."""
        resp = requests.post(
            f"{HA_URL}/api/services/ssh_command/execute?return_response",
            json={
                "host": "192.0.2.1",
                "username": "user",
                "password": "pass",
                "command": "echo hi",
                "check_known_hosts": False,
            },
            timeout=10,
        )
        assert resp.status_code == 401, resp.text

    def test_known_hosts_conflict_rejected(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Supplying known_hosts with check_known_hosts=False is rejected."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo hi",
                "check_known_hosts": False,
                "known_hosts": "/tmp/known_hosts_conflict",
            },
        )
        assert resp.status_code == 400, resp.text

    def test_no_credentials_rejected(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """A service call that omits both password and key_file is rejected."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "command": "echo hi",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 400, resp.text

    def test_successful_auth_uses_encrypted_connection(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """A successful SSH command is executed (implying an encrypted SSH session)."""
        # asyncssh always uses encrypted connections; we verify the round-trip succeeds.
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo encrypted_conn_ok",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 200, resp.text
        assert "encrypted_conn_ok" in svc_data(resp)["output"]
