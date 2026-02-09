"""The SSH Command integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
from aiofiles import open as aioopen
from aiofiles.ospath import exists
from asyncssh import HostKeyNotVerifiable, PermissionDenied, connect, read_known_hosts

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_HOST, CONF_COMMAND, CONF_TIMEOUT, CONF_ERROR
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, ServiceResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from .const import DOMAIN, SERVICE_EXECUTE, CONF_KEY_FILE, CONF_INPUT, CONST_DEFAULT_TIMEOUT, \
    CONF_CHECK_KNOWN_HOSTS, CONF_KNOWN_HOSTS, CONF_CLIENT_KEYS, CONF_CHECK, CONF_OUTPUT, CONF_EXIT_STATUS

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def _validate_service_data(data: dict[str, Any]) -> None:
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

    if has_key_file and not await exists(data[CONF_KEY_FILE]):
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


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def async_execute(service_call: ServiceCall) -> ServiceResponse:
        await _validate_service_data(service_call.data)
        host = service_call.data.get(CONF_HOST)
        username = service_call.data.get(CONF_USERNAME)
        password = service_call.data.get(CONF_PASSWORD)
        key_file = service_call.data.get(CONF_KEY_FILE)
        command = service_call.data.get(CONF_COMMAND)
        input_data = service_call.data.get(CONF_INPUT)
        check_known_hosts = service_call.data.get(CONF_CHECK_KNOWN_HOSTS, True)
        known_hosts = service_call.data.get(CONF_KNOWN_HOSTS)
        timeout = service_call.data.get(CONF_TIMEOUT, CONST_DEFAULT_TIMEOUT)

        if input_data:
            if await exists(input_data):
                # input is a file path, read it and send content as input
                async with aioopen(input_data, 'r') as sf:
                    input_data = await sf.read()

        conn_kwargs = {
            CONF_HOST: host,
            CONF_USERNAME: username,
            CONF_PASSWORD: password,
            CONF_CLIENT_KEYS: key_file,
        }

        if check_known_hosts:
            if not known_hosts:
                known_hosts = str(Path('~', '.ssh', CONF_KNOWN_HOSTS).expanduser())
            if await exists(known_hosts):
                # open the known hosts file asynchronously, otherwise Home Assistant will complain about blocking I/O
                conn_kwargs[CONF_KNOWN_HOSTS] = await hass.async_add_executor_job(read_known_hosts, known_hosts)
            else:
                conn_kwargs[CONF_KNOWN_HOSTS] = known_hosts
        else:
            conn_kwargs[CONF_KNOWN_HOSTS] = None

        run_kwargs = {
            CONF_COMMAND: command,
            CONF_CHECK: False,
            CONF_TIMEOUT: timeout,
        }

        if input_data:
            run_kwargs[CONF_INPUT] = input_data

        try:
            async with connect(**conn_kwargs) as conn:
                result = await conn.run(**run_kwargs)
        except HostKeyNotVerifiable:
            raise ServiceValidationError(
                "The host key could not be verified.",
                translation_domain=DOMAIN,
                translation_key="host_key_not_verifiable",
            )
        except PermissionDenied:
            raise ServiceValidationError(
                "SSH login failed.",
                translation_domain=DOMAIN,
                translation_key="login_failed",
            )
        except TimeoutError:
            raise ServiceValidationError(
                "Connection timed out.",
                translation_domain=DOMAIN,
                translation_key="connection_timed_out",
            )
        except OSError as e:
            if e.strerror == 'Temporary failure in name resolution':
                raise ServiceValidationError(
                    "Host is not reachable.",
                    translation_domain=DOMAIN,
                    translation_key="host_not_reachable",
                )
            raise e

        return {
            CONF_OUTPUT: result.stdout,
            CONF_ERROR: result.stderr,
            CONF_EXIT_STATUS: result.exit_status,
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE,
        async_execute,
        schema=SERVICE_EXECUTE_SCHEMA,
        supports_response=SupportsResponse.ONLY
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SSH Command from a config entry. Nothing to do here."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry. Nothing to do here."""
    return True
