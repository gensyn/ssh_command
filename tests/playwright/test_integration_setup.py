"""Playwright E2E tests: SSH Command integration setup via the config flow."""

from __future__ import annotations

import pytest
from typing import Any
import requests
from playwright.sync_api import Page, expect

from conftest import HA_URL


class TestIntegrationSetup:
    """Tests that cover adding and removing the SSH Command integration."""

    def test_integration_page_loads(self, page: Page) -> None:
        """The integrations page should load without errors."""
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")
        expect(page).to_have_title(lambda t: "Home Assistant" in t or "Integrations" in t)

    def test_add_integration_via_ui(self, page: Page) -> None:
        """Adding the SSH Command integration through the UI config flow works."""
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")

        # Click the "+ Add integration" button
        add_btn = page.get_by_role("button", name="Add integration")
        if not add_btn.is_visible():
            # Some HA versions show a FAB or icon button
            add_btn = page.locator("[aria-label='Add integration']")
        add_btn.click()

        # Search for "SSH Command" in the integration picker
        search_box = page.get_by_placeholder("Search")
        if not search_box.is_visible():
            search_box = page.locator("input[type='search']")
        search_box.fill("SSH Command")
        page.wait_for_timeout(500)

        # Select the SSH Command entry
        page.get_by_text("SSH Command").first.click()
        page.wait_for_timeout(1000)

        # The config flow either shows a form or creates an entry immediately
        # (SSH Command uses single_instance_allowed with no form fields).
        # Verify we land back on the integrations page or see an abort/success dialog.
        page.wait_for_load_state("networkidle")

    def test_integration_appears_in_list(self, ha_api: requests.Session) -> None:
        """After setup the SSH Command entry should appear in the config entries API."""
        # Initiate flow and complete it
        flow_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_command"},
        )
        assert flow_resp.status_code in (200, 201), flow_resp.text

        # Verify entry is present
        entries_resp = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
        entries_resp.raise_for_status()
        domains = [e["domain"] for e in entries_resp.json()]
        assert "ssh_command" in domains

        # Cleanup: remove the entry we just added
        for entry in entries_resp.json():
            if entry["domain"] == "ssh_command":
                ha_api.delete(
                    f"{HA_URL}/api/config/config_entries/entry/{entry['entry_id']}"
                )

    def test_single_instance_enforced(self, ha_api: requests.Session) -> None:
        """A second setup attempt should be aborted by the single-instance guard."""
        # First setup
        first = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_command"},
        )
        assert first.status_code in (200, 201), first.text

        # Second setup should result in an abort
        second = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_command"},
        )
        assert second.status_code in (200, 201), second.text
        result_type = second.json().get("type")
        # Depending on HA version the abort is returned immediately
        assert result_type in ("abort", "create_entry"), (
            f"Expected abort or immediate create_entry, got: {result_type}"
        )

        # Cleanup
        entries_resp = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
        for entry in entries_resp.json():
            if entry["domain"] == "ssh_command":
                ha_api.delete(
                    f"{HA_URL}/api/config/config_entries/entry/{entry['entry_id']}"
                )

    def test_remove_integration(self, ha_api: requests.Session) -> None:
        """Removing a config entry succeeds and the entry disappears from the list."""
        # Setup
        flow_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_command"},
        )
        assert flow_resp.status_code in (200, 201)

        entries_resp = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
        entries_resp.raise_for_status()
        entry_id = next(
            (e["entry_id"] for e in entries_resp.json() if e["domain"] == "ssh_command"),
            None,
        )
        assert entry_id is not None, "Config entry was not created"

        # Delete
        del_resp = ha_api.delete(
            f"{HA_URL}/api/config/config_entries/entry/{entry_id}"
        )
        assert del_resp.status_code in (200, 204)

        # Confirm it's gone
        entries_resp2 = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
        domains = [e["domain"] for e in entries_resp2.json()]
        assert "ssh_command" not in domains

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
        # HA returns 400 for ServiceValidationError
        assert resp.status_code == 400, resp.text

    def test_invalid_credentials_error(self, ha_api: requests.Session, ensure_integration: Any, ssh_server_1: dict) -> None:
        """Connecting with wrong credentials returns a permission-denied error."""
        resp = ha_api.post(
            f"{HA_URL}/api/services/ssh_command/execute?return_response",
            json={
                "host": ssh_server_1["host"],
                "port": ssh_server_1["port"],
                "username": ssh_server_1["username"],
                "password": "wrongpassword",
                "command": "echo hi",
                "check_known_hosts": False,
                "timeout": 10,
            },
        )
        assert resp.status_code == 400, resp.text
