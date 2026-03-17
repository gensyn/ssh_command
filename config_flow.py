"""Config flow for the SSH Command integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigFlow

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult

from .const import DOMAIN


class SshCommandConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SSH Command."""

    VERSION = 1
    single_instance_allowed = True

    async def async_step_user(
            self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        return self.async_create_entry(title="SSH Command", data={})
