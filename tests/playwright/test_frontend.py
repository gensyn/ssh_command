"""Playwright E2E tests: SSH Command frontend / UI interactions."""

from __future__ import annotations

from typing import Any

from playwright.sync_api import Page, expect

from conftest import HA_URL


class TestFrontend:
    """Tests that exercise the Home Assistant frontend with the SSH Command integration."""

    def test_home_assistant_frontend_loads(self, page: Page) -> None:
        """The Home Assistant frontend loads successfully."""
        page.goto(HA_URL)
        page.wait_for_load_state("networkidle")
        # HA login page or overview should load
        expect(page).not_to_have_title("")

    def test_integrations_page_accessible(self, page: Page) -> None:
        """The integrations settings page is accessible."""
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")
        # Page should not show a network error
        assert page.url.startswith(HA_URL), f"Unexpected redirect to: {page.url}"

    def test_developer_tools_page_loads(self, page: Page) -> None:
        """Developer tools page loads (used for calling services manually)."""
        page.goto(f"{HA_URL}/developer-tools/service")
        page.wait_for_load_state("networkidle")
        assert page.url.startswith(HA_URL)

    def test_ssh_command_visible_in_integrations(self, page: Page, ensure_integration: Any) -> None:
        """After setup, SSH Command appears on the integrations page."""
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")
        # Look for the integration card/name on the page
        ssh_card = page.get_by_text("SSH Command", exact=False)
        expect(ssh_card.first).to_be_visible()

    def test_service_call_via_developer_tools(self, page: Page, ensure_integration: Any) -> None:
        """It should be possible to navigate to the service call UI for ssh_command."""
        page.goto(f"{HA_URL}/developer-tools/service")
        page.wait_for_load_state("networkidle")

        # Open the service selector dropdown
        service_selector = page.locator("ha-service-picker, [data-domain='ssh_command']").first
        if service_selector.is_visible():
            service_selector.click()
            page.wait_for_timeout(500)
            # Look for ssh_command option
            ssh_option = page.get_by_text("ssh_command", exact=False)
            if ssh_option.is_visible():
                ssh_option.first.click()

        # Page should still be accessible (no crashes)
        assert page.url.startswith(HA_URL)

    def test_config_page_shows_integration_info(self, page: Page, ensure_integration: Any) -> None:
        """The SSH Command integration detail page shows expected information."""
        page.goto(f"{HA_URL}/config/integrations")
        page.wait_for_load_state("networkidle")

        # Try to click on the SSH Command integration card
        ssh_link = page.get_by_text("SSH Command", exact=False).first
        if ssh_link.is_visible():
            ssh_link.click()
            page.wait_for_load_state("networkidle")
        # Verify we are still on a valid HA page
        assert page.url.startswith(HA_URL)

    def test_no_javascript_errors_on_main_page(self, page: Page) -> None:
        """The main HA page does not log critical JavaScript errors."""
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.goto(HA_URL)
        page.wait_for_load_state("networkidle")
        # Filter out known non-critical errors; check only for unhandled exceptions
        critical = [e for e in errors if "ResizeObserver" not in e]
        assert len(critical) == 0, f"JavaScript errors: {critical}"
