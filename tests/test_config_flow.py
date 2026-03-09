"""Tests for the SSH Command config flow."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ssh_command.config_flow import SshCommandConfigFlow
from ssh_command.const import DOMAIN


def _make_flow(hass, existing_entries=None):
    """Instantiate a :class:`SshCommandConfigFlow` with a minimal mock context."""
    flow = SshCommandConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    entries = existing_entries if existing_entries is not None else []
    flow._async_current_entries = lambda: entries
    return flow


@pytest.mark.asyncio
async def test_user_step_creates_entry(hass):
    """First user setup creates a config entry."""
    flow = _make_flow(hass)

    result = await flow.async_step_user()

    assert result["type"] == "create_entry"
    assert result["title"] == "SSH Command"
    assert result["data"] == {}


@pytest.mark.asyncio
async def test_user_step_single_instance_existing_entries(hass):
    """Setup is aborted when a config entry already exists."""
    flow = _make_flow(hass, existing_entries=[MagicMock()])

    result = await flow.async_step_user()

    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.asyncio
async def test_user_step_single_instance_hass_data(hass):
    """Setup is aborted when DOMAIN is present in hass.data."""
    hass.data[DOMAIN] = object()
    flow = _make_flow(hass)

    result = await flow.async_step_user()

    assert result["type"] == "abort"
    assert result["reason"] == "single_instance_allowed"
