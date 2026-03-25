"""Playwright E2E tests: SSH Command configuration management."""

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


class TestConfiguration:
    """Tests covering configuration options of the SSH Command integration."""

    def test_default_timeout_accepted(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Omitting the timeout field uses the default (30 s) and the call succeeds."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo default_timeout",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 200, resp.text
        assert "default_timeout" in svc_data(resp)["output"]

    def test_custom_timeout_accepted(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """An explicit timeout value is accepted by the service schema."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo custom_timeout",
                "check_known_hosts": False,
                "timeout": 20,
            },
        )
        assert resp.status_code == 200, resp.text
        assert "custom_timeout" in svc_data(resp)["output"]

    def test_check_known_hosts_false(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Setting check_known_hosts=False bypasses host verification."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo no_host_check",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 200, resp.text
        assert "no_host_check" in svc_data(resp)["output"]

    def test_known_hosts_with_check_disabled_rejected(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Providing known_hosts while check_known_hosts=False is a validation error."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo hi",
                "check_known_hosts": False,
                "known_hosts": "/tmp/known_hosts",
            },
        )
        assert resp.status_code == 400, resp.text

    def test_password_auth_configuration(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Password-based authentication is accepted and works against the test server."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo password_auth",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 200, resp.text
        assert "password_auth" in svc_data(resp)["output"]

    def test_key_file_not_found_rejected(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Providing a non-existent key_file path results in a validation error."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "key_file": "/nonexistent/id_rsa",
                "command": "echo hi",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 400, resp.text

    def test_multiple_servers_independent(
        self,
        ha_api: requests.Session,
        ensure_integration: Any,
        ssh_server_1: dict,
        ssh_server_2: dict,
    ) -> None:
        """Commands can be sent to two different SSH servers independently."""
        resp1 = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo server1",
                "check_known_hosts": False,
            },
        )
        resp2 = execute(
            ha_api,
            {
                "host": ssh_server_2["host"],
                "username": ssh_server_2["username"],
                "password": ssh_server_2["password"],
                "command": "echo server2",
                "check_known_hosts": False,
            },
        )
        assert resp1.status_code == 200, resp1.text
        assert resp2.status_code == 200, resp2.text
        assert "server1" in svc_data(resp1)["output"]
        assert "server2" in svc_data(resp2)["output"]

    def test_username_configuration(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """The username field is correctly forwarded to the SSH connection."""
        resp = execute(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "whoami",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 200, resp.text
        output = svc_data(resp)["output"].strip()
        assert output == ssh_server_1["username"]
