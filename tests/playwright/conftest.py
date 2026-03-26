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
# Each SSH test server is a separate container (both on port 22, the default).
SSH_HOST_1: str = os.environ.get("SSH_HOST_1", "ssh_docker_test_1")
SSH_HOST_2: str = os.environ.get("SSH_HOST_2", "ssh_docker_test_2")
SSH_USER: str = os.environ.get("SSH_USER", "foo")
SSH_PASSWORD: str = os.environ.get("SSH_PASSWORD", "pass")

HA_USERNAME: str = os.environ.get("HA_USERNAME", "admin")
HA_PASSWORD: str = os.environ.get("HA_PASSWORD", "admin")

# Paths on the HA container's filesystem populated by ssh_docker_test_1's
# startup script (see tests/playwright/ssh-init-entrypoint.sh).
# ssh_test_init volume is mounted read-only at /ssh-test-keys in the HA
# container, providing a user auth key and a known_hosts file for tests.
SSH_KEY_FILE: str = os.environ.get("SSH_KEY_FILE", "/ssh-test-keys/id_ed25519")
SSH_KNOWN_HOSTS: str = os.environ.get("SSH_KNOWN_HOSTS", "/ssh-test-keys/known_hosts")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HA_TOKEN: str | None = None


def get_ha_token() -> str:
    """Obtain a Home Assistant access token via the login flow.

    On the first call the token is fetched and cached for the remainder of
    the test session.  Retries up to 5 times with a short delay to handle
    the window immediately after HA onboarding completes.
    """
    global _HA_TOKEN  # noqa: PLW0603
    if _HA_TOKEN:
        return _HA_TOKEN

    last_exc: Exception | None = None
    for attempt in range(5):
        if attempt:
            time.sleep(5)
        try:
            session = requests.Session()

            # 1. Initiate the login flow
            flow_resp = session.post(
                f"{HA_URL}/auth/login_flow",
                json={
                    "client_id": f"{HA_URL}/",
                    "handler": ["homeassistant", None],
                    "redirect_uri": f"{HA_URL}/",
                },
                timeout=30,
            )
            flow_resp.raise_for_status()
            flow_id = flow_resp.json()["flow_id"]

            # 2. Submit credentials
            cred_resp = session.post(
                f"{HA_URL}/auth/login_flow/{flow_id}",
                json={
                    "username": HA_USERNAME,
                    "password": HA_PASSWORD,
                    "client_id": f"{HA_URL}/",
                },
                timeout=30,
            )
            cred_resp.raise_for_status()
            cred_data = cred_resp.json()
            if cred_data.get("type") != "create_entry":
                raise RuntimeError(
                    f"Login flow did not complete: type={cred_data.get('type')!r}, "
                    f"errors={cred_data.get('errors')}"
                )
            auth_code = cred_data["result"]

            # 3. Exchange code for token
            token_resp = session.post(
                f"{HA_URL}/auth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": auth_code,
                    "client_id": f"{HA_URL}/",
                },
                timeout=30,
            )
            token_resp.raise_for_status()
            _HA_TOKEN = token_resp.json()["access_token"]
            return _HA_TOKEN
        except Exception as exc:  # noqa: BLE001
            last_exc = exc

    raise RuntimeError(f"Failed to obtain HA token after 5 attempts: {last_exc}") from last_exc


def wait_for_ha(timeout: int = 300) -> None:
    """Block until Home Assistant is fully started and accepts API requests.

    Polls GET /api/onboarding which requires no authentication and therefore
    cannot trigger HA's IP-ban mechanism.  The endpoint returns HTTP 200 even
    during onboarding, so it is safe to use as a startup indicator.

    A second pass waits for the integration to be loadable (the custom
    component may still be installing its requirements).
    """
    deadline = time.time() + timeout

    # Phase 1: wait for the web server to respond at all
    while time.time() < deadline:
        try:
            resp = requests.get(f"{HA_URL}/api/onboarding", timeout=5)
            if resp.status_code == 200:
                break
        except requests.RequestException:
            pass
        time.sleep(3)
    else:
        raise RuntimeError(f"Home Assistant did not become ready within {timeout}s")

    # Phase 2: wait for the config-entries API to be usable (integrations loaded)
    # We use a small fixed delay to let HA finish loading custom components and
    # installing their requirements (asyncssh etc.) after the web server is up.
    time.sleep(15)



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
    """Provide an authenticated browser context for Home Assistant.

    The HA frontend reads ``hassTokens`` from ``localStorage`` to determine
    whether the user is authenticated.  Using Playwright's ``storage_state``
    pre-populates ``localStorage`` *before* the first navigation, which is
    more reliable than ``add_init_script`` (the latter can lose a race with
    HA's own auth-check code and cause a redirect to ``/onboarding.html``).
    """
    hass_tokens = json.dumps({
        "access_token": ha_token,
        "token_type": "Bearer",
        "expires_in": 1800,
        "hassUrl": HA_URL,
        "clientId": f"{HA_URL}/",
        "expires": int(time.time() * 1000) + 1_800_000,
        "refresh_token": "",
    })
    ctx = browser.new_context(
        base_url=HA_URL,
        storage_state={
            "cookies": [],
            "origins": [
                {
                    "origin": HA_URL,
                    "localStorage": [
                        {"name": "hassTokens", "value": hass_tokens},
                    ],
                }
            ],
        },
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
    """Return connection parameters for SSH Test Server 1.

    The server runs sshd on the standard port 22, which the Home Assistant
    integration uses by default.
    """
    return {
        "host": SSH_HOST_1,
        "username": SSH_USER,
        "password": SSH_PASSWORD,
    }


@pytest.fixture(scope="session")
def ssh_server_2() -> dict:
    """Return connection parameters for SSH Test Server 2.

    A separate container from ssh_server_1 so the two servers are genuinely
    independent (different hostnames).
    """
    return {
        "host": SSH_HOST_2,
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

    After the test the environment is restored to its exact pre-test state:
    - Any entries added during the test are removed.
    - Any entries that were present before but removed during the test are
      re-added, so subsequent test runs start from the same baseline.
    """
    # Snapshot state before the test
    resp = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
    resp.raise_for_status()
    entries_before: set[str] = {
        e["entry_id"]
        for e in resp.json()
        if e.get("domain") == "ssh_command"
    }

    # There should be not entry
    assert not entries_before

    # If the integration is not yet configured, add it now
    flow_resp = ha_api.post(
        f"{HA_URL}/api/config/config_entries/flow",
        json={"handler": "ssh_command"},
    )
    flow_resp.raise_for_status()

    yield

    # --- Teardown: restore pre-test state ---
    resp = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
    resp.raise_for_status()
    entries_after: set[str] = {
        e["entry_id"]
        for e in resp.json()
        if e.get("domain") == "ssh_command"
    }

    # Remove entries that were added during the test
    for entry_id in entries_after - entries_before:
        ha_api.delete(f"{HA_URL}/api/config/config_entries/entry/{entry_id}")

def _get_ssh_command_entry_ids(ha_api: requests.Session) -> set[str]:
    """Return the set of current ssh_command config-entry IDs."""
    resp = ha_api.get(f"{HA_URL}/api/config/config_entries/entry")
    resp.raise_for_status()
    return {e["entry_id"] for e in resp.json() if e.get("domain") == "ssh_command"}


def _add_integration(ha_api: requests.Session) -> None:
    """Initiate the SSH Command config flow.

    The call starts the config flow; Home Assistant will immediately complete
    it and create the single config entry (SSH Command has no form fields and
    single_instance_allowed=True).  The HTTP response status is validated but
    the caller is responsible for confirming the resulting entry state when
    strict verification is needed.
    """
    resp = ha_api.post(
        f"{HA_URL}/api/config/config_entries/flow",
        json={"handler": "ssh_command"},
    )
    resp.raise_for_status()


def _remove_all_ssh_command_entries(ha_api: requests.Session) -> None:
    """Delete every ssh_command config entry from Home Assistant."""
    for entry_id in _get_ssh_command_entry_ids(ha_api):
        ha_api.delete(f"{HA_URL}/api/config/config_entries/entry/{entry_id}")
