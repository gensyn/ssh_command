"""Config flow for the SSH Command integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class SshCommandConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SSH Command."""

    VERSION = 1

    async def async_step_user(
            self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        # Check if already configured
        if self._async_current_entries() or self.hass.data.get(DOMAIN):  # pylint: disable=no-member
            return self.async_abort(reason="single_instance_allowed")

        return self.async_create_entry(title="SSH Command", data={})
