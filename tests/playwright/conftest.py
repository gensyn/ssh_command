"""Pytest configuration and fixtures for SSH Command Playwright E2E tests."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Generator

import pytest
import requests
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

# ---------------------------------------------------------------------------
# Environment-variable driven configuration
# ---------------------------------------------------------------------------

HA_URL: str = os.environ.get("HOMEASSISTANT_URL", "http://homeassistant:8123")
SSH_HOST: str = os.environ.get("SSH_HOST", "ssh_docker_test")
SSH_PORT_1: int = int(os.environ.get("SSH_PORT_1", "2222"))
SSH_PORT_2: int = int(os.environ.get("SSH_PORT_2", "2223"))
SSH_USER: str = os.environ.get("SSH_USER", "foo")
SSH_PASSWORD: str = os.environ.get("SSH_PASSWORD", "pass")

HA_USERNAME: str = os.environ.get("HA_USERNAME", "admin")
HA_PASSWORD: str = os.environ.get("HA_PASSWORD", "admin")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HA_TOKEN: str | None = None


def get_ha_token() -> str:
    """Obtain a long-lived Home Assistant access token via the REST API.

    On the first call the token is fetched and cached for the remainder of
    the test session.
    """
    global _HA_TOKEN  # noqa: PLW0603
    if _HA_TOKEN:
        return _HA_TOKEN

    # 1. Fetch the CSRF token from the login page
    session = requests.Session()
    login_page = session.get(f"{HA_URL}/auth/login_flow", timeout=30)
    login_page.raise_for_status()

    # 2. Initiate the login flow
    flow_resp = session.post(
        f"{HA_URL}/auth/login_flow",
        json={"client_id": HA_URL, "handler": ["homeassistant", None], "redirect_uri": f"{HA_URL}/"},
        timeout=30,
    )
    flow_resp.raise_for_status()
    flow_id = flow_resp.json()["flow_id"]

    # 3. Submit credentials
    cred_resp = session.post(
        f"{HA_URL}/auth/login_flow/{flow_id}",
        json={"username": HA_USERNAME, "password": HA_PASSWORD, "client_id": HA_URL},
        timeout=30,
    )
    cred_resp.raise_for_status()
    auth_code = cred_resp.json().get("result")

    # 4. Exchange code for token
    token_resp = session.post(
        f"{HA_URL}/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": HA_URL,
        },
        timeout=30,
    )
    token_resp.raise_for_status()
    _HA_TOKEN = token_resp.json()["access_token"]
    return _HA_TOKEN


def wait_for_ha(timeout: int = 120) -> None:
    """Block until Home Assistant is ready to accept connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(f"{HA_URL}/api/", timeout=5)
            if resp.status_code in (200, 401):
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError(f"Home Assistant did not become ready within {timeout}s")


# ---------------------------------------------------------------------------
# Session-scoped Playwright fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def playwright_instance() -> Generator[Playwright, None, None]:
    """Provide a session-scoped Playwright instance."""
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Generator[Browser, None, None]:
    """Provide a session-scoped Chromium browser."""
    browser = playwright_instance.chromium.launch(headless=True)
    yield browser
    browser.close()


@pytest.fixture(scope="session")
def ha_base_url() -> str:
    """Return the configured Home Assistant base URL."""
    return HA_URL


@pytest.fixture(scope="session")
def ha_token() -> str:
    """Provide a valid Home Assistant long-lived access token."""
    wait_for_ha()
    return get_ha_token()


# ---------------------------------------------------------------------------
# Per-test browser context with an authenticated HA session
# ---------------------------------------------------------------------------


@pytest.fixture()
def context(browser: Browser, ha_token: str) -> Generator[BrowserContext, None, None]:
    """Provide an authenticated browser context for Home Assistant."""
    ctx = browser.new_context(
        base_url=HA_URL,
        extra_http_headers={"Authorization": f"Bearer {ha_token}"},
    )
    # Inject the token into localStorage so the HA frontend recognises the session.
    # Use json.dumps to safely escape all values before embedding in JS.
    token_json = json.dumps(ha_token)
    ha_url_json = json.dumps(HA_URL)
    ctx.add_init_script(
        f"""
        window.localStorage.setItem(
            'hassTokens',
            JSON.stringify({{
                access_token: {token_json},
                token_type: 'Bearer',
                expires_in: 1800,
                hassUrl: {ha_url_json},
                clientId: {ha_url_json},
                expires: Date.now() + 1800000,
                refresh_token: ''
            }})
        );
        """
    )
    yield ctx
    ctx.close()


@pytest.fixture()
def page(context: BrowserContext) -> Generator[Page, None, None]:
    """Provide a fresh page within the authenticated browser context."""
    pg = context.new_page()
    yield pg
    pg.close()


# ---------------------------------------------------------------------------
# SSH server fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def ssh_server_1() -> dict:
    """Return connection parameters for SSH Test Server 1."""
    return {
        "host": SSH_HOST,
        "port": SSH_PORT_1,
        "username": SSH_USER,
        "password": SSH_PASSWORD,
    }


@pytest.fixture(scope="session")
def ssh_server_2() -> dict:
    """Return connection parameters for SSH Test Server 2."""
    return {
        "host": SSH_HOST,
        "port": SSH_PORT_2,
        "username": SSH_USER,
        "password": SSH_PASSWORD,
    }


# ---------------------------------------------------------------------------
# Integration setup / teardown helper
# ---------------------------------------------------------------------------


@pytest.fixture()
def ha_api(ha_token: str) -> requests.Session:
    """Return a requests Session pre-configured to call the HA REST API."""
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {ha_token}"
    session.headers["Content-Type"] = "application/json"
    return session


@pytest.fixture()
def ensure_integration(ha_api: requests.Session) -> Generator[None, None, None]:
    """Ensure the SSH Command integration is set up before a test runs.

    Tears down the integration (removes the config entry) after the test.
    """
    # Check whether the integration is already configured
    resp = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
    resp.raise_for_status()
    entries_before = {
        e["entry_id"]
        for e in resp.json()
        if e.get("domain") == "ssh_command"
    }

    # If not present, initiate the config flow
    if not entries_before:
        flow_resp = ha_api.post(
            f"{HA_URL}/api/config/config_entries/flow",
            json={"handler": "ssh_command"},
        )
        flow_resp.raise_for_status()

    yield

    # Teardown: remove any entries that were added during the test
    resp = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
    resp.raise_for_status()
    for entry in resp.json():
        if entry.get("domain") == "ssh_command" and entry["entry_id"] not in entries_before:
            ha_api.delete(f"{HA_URL}/api/config/config_entries/entry/{entry['entry_id']}")
