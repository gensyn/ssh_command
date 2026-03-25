"""The SSH Command integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_HOST, CONF_COMMAND, CONF_TIMEOUT
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, ServiceResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from .const import DOMAIN, SERVICE_EXECUTE, CONF_KEY_FILE, CONF_INPUT, CONST_DEFAULT_TIMEOUT, \
    CONF_CHECK_KNOWN_HOSTS, CONF_KNOWN_HOSTS
from .coordinator import SshCommandCoordinator

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)  # pylint: disable=invalid-name


async def _validate_service_data(hass: HomeAssistant, data: dict[str, Any]) -> None:
    has_password: bool = bool(data.get(CONF_PASSWORD))
    has_key_file: bool = bool(data.get(CONF_KEY_FILE))

    if not has_password and not has_key_file:
        raise ServiceValidationError(
            "Either password or key file must be provided.",
            translation_domain=DOMAIN,
            translation_key="password_or_key_file_required",
        )

    has_command: bool = bool(data.get(CONF_COMMAND))
    has_input: bool = bool(data.get(CONF_INPUT))

    if not has_command and not has_input:
        raise ServiceValidationError(
            "Either command or input must be provided.",
            translation_domain=DOMAIN,
            translation_key="command_or_input",
        )

    if has_key_file and not await hass.async_add_executor_job(Path(data[CONF_KEY_FILE]).exists):
        raise ServiceValidationError(
            "Could not find key file.",
            translation_domain=DOMAIN,
            translation_key="key_file_not_found",
        )

    has_known_hosts: bool = bool(data.get(CONF_KNOWN_HOSTS))

    if has_known_hosts and data.get(CONF_CHECK_KNOWN_HOSTS, True) is False:
        raise ServiceValidationError(
            "Known hosts provided while check known hosts is disabled.",
            translation_domain=DOMAIN,
            translation_key="known_hosts_with_check_disabled",
        )


SERVICE_EXECUTE_SCHEMA = vol.Schema(
    vol.All(
        {
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_USERNAME): str,
            vol.Optional(CONF_PASSWORD): str,
            vol.Optional(CONF_KEY_FILE): str,
            vol.Optional(CONF_COMMAND): str,
            vol.Optional(CONF_INPUT): str,
            vol.Optional(CONF_CHECK_KNOWN_HOSTS, default=True): bool,
            vol.Optional(CONF_KNOWN_HOSTS): str,
            vol.Optional(CONF_TIMEOUT, default=CONST_DEFAULT_TIMEOUT): int,
        }
    )
)


async def async_setup(hass: HomeAssistant, _config: ConfigType) -> bool:
    """Set up the SSH Command integration."""
    hass.data.setdefault(DOMAIN, {})

    async def async_execute(service_call: ServiceCall) -> ServiceResponse:
        await _validate_service_data(hass, service_call.data)
        # ssh_command is a single-instance integration (enforced by single_instance_allowed
        # in the config flow), so there is at most one coordinator in hass.data[DOMAIN].
        coordinator = next(iter(hass.data.get(DOMAIN, {}).values()), None)
        if coordinator is None:
            raise ServiceValidationError(
                "SSH Command integration is not set up.",
                translation_domain=DOMAIN,
                translation_key="integration_not_set_up",
            )
        return await coordinator.async_execute(service_call.data)

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE,
        async_execute,
        schema=SERVICE_EXECUTE_SCHEMA,
        supports_response=SupportsResponse.ONLY
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SSH Command from a config entry."""
    coordinator = SshCommandCoordinator(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True
