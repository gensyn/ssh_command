"""Playwright E2E tests: SSH Command integration setup via the config flow."""

from __future__ import annotations

from typing import Any

import requests

from conftest import (
    HA_URL,
    _get_ssh_command_entry_ids,
    _remove_all_ssh_command_entries,
)


class TestIntegrationSetup:
    """Tests that cover adding and removing the SSH Command integration."""

    def test_connection_error_handling(self, ha_api: requests.Session, ensure_integration: Any) -> None:
        """Calling execute with an unreachable host raises a validation error."""
        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_command/execute?return_response",
            json={
                "host": "192.0.2.1",  # RFC 5737 TEST-NET – guaranteed unreachable
                "username": "nobody",
                "password": "nopass",
                "command": "echo hi",
                "check_known_hosts": False,
                "timeout": 5,
            },
        )
        # HA returns 500 for ServiceValidationError
        assert resp.status_code == 500, resp.text

    def test_invalid_credentials_error(self, ha_api: requests.Session, ensure_integration: Any,
                                       ssh_server_1: dict) -> None:
        """Connecting with wrong credentials returns a permission-denied error."""
        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_command/execute?return_response",
            json={
                "host": ssh_server_1["host"],
                "username": ssh_server_1["username"],
                "password": "wrongpassword",
                "command": "echo hi",
                "check_known_hosts": False,
                "timeout": 10,
            },
        )
        assert resp.status_code == 500, resp.text


class TestIntegrationLifecycle:
    """Single end-to-end lifecycle test covering all five requirements:

    1. Add the integration.
    2. Assert it cannot be added a second time.
    3. Send commands covering all service parameters.
    4. Remove the integration.
    5. Assert removal leaves the environment identical to its pre-test state
       so the test can be repeated with no side effects.
    """

    def test_full_lifecycle(self, ha_api: requests.Session, ssh_server_1: dict, ssh_server_2: dict) -> None:
        """Complete add → use → remove → verify-clean lifecycle."""

        # ------------------------------------------------------------------ #
        # 0. Precondition: start from a clean state (no integration present). #
        #    If a previous run left an entry behind, remove it first so this  #
        #    test is idempotent.                                                #
        # ------------------------------------------------------------------ #
        assert ssh_server_1["host"] != ssh_server_2["host"], (
            "ssh_server_1 and ssh_server_2 must be distinct servers for the multi-server scenario to be meaningful"
        )
        _remove_all_ssh_command_entries(ha_api)
        assert _get_ssh_command_entry_ids(ha_api) == set(), (
            "Precondition failed: ssh_command entries still present after cleanup"
        )

        # ------------------------------------------------------------------ #
        # 1. Add the integration via the config flow.                          #
        # ------------------------------------------------------------------ #
        add_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_command"},
        )
        assert add_resp.status_code in (200, 201), add_resp.text
        assert add_resp.json().get("type") == "create_entry", (
            f"Expected 'create_entry', got: {add_resp.json().get('type')!r}"
        )

        entry_ids_after_add = _get_ssh_command_entry_ids(ha_api)
        assert len(entry_ids_after_add) == 1, (
            f"Expected exactly 1 ssh_command entry, found: {len(entry_ids_after_add)}"
        )
        entry_id = next(iter(entry_ids_after_add))

        # ------------------------------------------------------------------ #
        # 2. Assert the integration cannot be added a second time.             #
        # ------------------------------------------------------------------ #
        second_add = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_command"},
        )
        assert second_add.status_code in (200, 201), second_add.text
        assert second_add.json().get("type") == "abort", (
            f"Expected 'abort' on second add, got: {second_add.json().get('type')!r}"
        )
        assert second_add.json().get("reason") == "single_instance_allowed"
        # Still exactly one entry – the second attempt must not create another
        assert _get_ssh_command_entry_ids(ha_api) == {entry_id}

        # ------------------------------------------------------------------ #
        # 3. Send commands covering all service parameters.                    #
        # ------------------------------------------------------------------ #
        def call(payload: dict) -> dict:
            r = ha_api.post(
                f"{HA_URL}/api/services/ssh_command/execute?return_response",
                json=payload,
            )
            assert r.status_code == 200, f"Service call failed: {r.text}"
            return r.json().get("service_response", r.json())

        base = {
            "host": ssh_server_1["host"],
            "username": ssh_server_1["username"],
            "password": ssh_server_1["password"],
            "check_known_hosts": False,
        }

        # host + username + password + command + check_known_hosts
        data = call({**base, "command": "echo hello"})
        assert "hello" in data["output"]
        assert data["exit_status"] == 0

        # timeout parameter
        data = call({**base, "command": "echo timeout_ok", "timeout": 15})
        assert "timeout_ok" in data["output"]

        # command writing to stderr
        data = call({**base, "command": "echo err_out >&2"})
        assert "err_out" in data["error"]

        # non-zero exit status
        data = call({**base, "command": "exit 2"})
        assert data["exit_status"] == 2

        # input parameter: send text to stdin via the 'cat' command
        data = call({**base, "command": "cat", "input": "stdin_content\n"})
        assert "stdin_content" in data["output"]

        # second SSH server
        base2 = {
            "host": ssh_server_2["host"],
            "username": ssh_server_2["username"],
            "password": ssh_server_2["password"],
            "check_known_hosts": False,
        }
        data = call({**base2, "command": "echo server2"})
        assert "server2" in data["output"]

        # ------------------------------------------------------------------ #
        # 4. Remove the integration.                                         #
        # ------------------------------------------------------------------ #
        del_resp = ha_api.delete(
            f"{HA_URL}/api/config/config_entries/entry/{entry_id}"
        )
        assert del_resp.status_code in (200, 204), del_resp.text

        # ------------------------------------------------------------------ #
        # 5. Assert removal and environment parity with pre-test state.      #
        # ------------------------------------------------------------------ #
        remaining = _get_ssh_command_entry_ids(ha_api)
        assert remaining == set(), (
            f"Expected no ssh_command entries after removal, found: {remaining}"
        )

        # Confirm the service is no longer usable (no coordinator present)
        no_integration_resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_command/execute?return_response",
            json={**base, "command": "echo hi"},
        )
        assert no_integration_resp.status_code >= 400, (
            "Service should return 400 when the integration is not configured"
        )

        # The test started with no integration and ends with no integration –
        # running it again will follow exactly the same path.
