"""Playwright E2E tests: ssh_command.execute service behaviour."""

from __future__ import annotations

from typing import Any

import requests

from conftest import HA_URL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def call_service(ha_api: requests.Session, payload: dict) -> requests.Response:
    """POST to the ssh_command execute service and return the raw response."""
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


class TestServices:
    """Tests focused on the HA service interface of SSH Command."""

    def test_service_registered(self, ha_api: requests.Session, ensure_integration: Any) -> None:
        """The ssh_command.execute service should appear in the HA services list."""
        resp = ha_api.get(f"{HA_URL}/api/services")
        resp.raise_for_status()
        services = resp.json()
        domains = {svc["domain"] for svc in services}
        assert "ssh_command" in domains

        ssh_services = next(
            (svc for svc in services if svc["domain"] == "ssh_command"), None
        )
        assert ssh_services is not None
        assert "execute" in ssh_services.get("services", {})

    def test_service_returns_response(self, ha_api: requests.Session, ensure_integration: Any,
                                      ssh_server_1: dict) -> None:
        """The service returns a structured response with output/error/exit_status."""
        resp = call_service(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo response_test",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 200, resp.text
        data = svc_data(resp)
        assert "output" in data
        assert "error" in data
        assert "exit_status" in data

    def test_service_echo_output(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """The service captures stdout from the remote command."""
        resp = call_service(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo service_output_check",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 200, resp.text
        assert "service_output_check" in svc_data(resp)["output"]

    def test_service_with_exit_status_error(self, ha_api: requests.Session, ensure_integration: Any,
                                            ssh_server_1: dict) -> None:
        """A command that exits with a non-zero code is still returned as 200 with the exit code."""
        resp = call_service(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "exit 1",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 200, resp.text
        assert svc_data(resp)["exit_status"] == 1

    def test_service_requires_integration_setup(self, ha_api: requests.Session) -> None:
        """Calling the service without a configured integration returns 400."""
        # Make sure no integration is set up
        entries_resp = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
        for entry in entries_resp.json():
            if entry["domain"] == "ssh_command":
                ha_api.delete(
                    f"{HA_URL}/api/config/config_entries/entry/{entry['entry_id']}"
                )

        resp = call_service(
            ha_api,
            {
                "host": "192.0.2.1",
                "username": "user",
                "password": "pass",
                "command": "echo hi",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code >= 400, resp.text

    def test_service_validation_missing_auth(self, ha_api: requests.Session, ensure_integration: Any,
                                             ssh_server_1: dict) -> None:
        """The service rejects calls that lack both password and key_file."""
        resp = call_service(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "command": "echo hi",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code >= 400, resp.text

    def test_service_validation_missing_command_and_input(self, ha_api: requests.Session, ensure_integration: Any,
                                                          ssh_server_1: dict) -> None:
        """The service rejects calls that lack both command and input."""
        resp = call_service(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "check_known_hosts": False,
            },
        )
        assert resp.status_code >= 400, resp.text

    def test_service_with_timeout_parameter(self, ha_api: requests.Session, ensure_integration: Any,
                                            ssh_server_1: dict) -> None:
        """The timeout parameter is accepted and used by the service."""
        resp = call_service(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo timeout_test",
                "check_known_hosts": False,
                "timeout": 15,
            },
        )
        assert resp.status_code == 200, resp.text
        assert "timeout_test" in svc_data(resp)["output"]

    def test_service_stderr_in_response(self, ha_api: requests.Session, ensure_integration: Any,
                                        ssh_server_1: dict) -> None:
        """Stderr output appears in the 'error' field of the service response."""
        resp = call_service(
            ha_api,
            {
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": ssh_server_1["password"],
                "command": "echo err_msg >&2",
                "check_known_hosts": False,
            },
        )
        assert resp.status_code == 200, resp.text
        assert "err_msg" in svc_data(resp)["error"]
