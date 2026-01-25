"""The SSH Command integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
from aiofiles import open as aioopen
from aiofiles.ospath import exists
from asyncssh import HostKeyNotVerifiable, PermissionDenied, connect, read_known_hosts

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_HOST, CONF_COMMAND, CONF_TIMEOUT
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, ServiceResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.typing import ConfigType
from .const import DOMAIN, SERVICE_EXECUTE, CONF_KEY_FILE, CONF_SCRIPT_FILE, CONST_DEFAULT_TIMEOUT, \
    CONF_CHECK_KNOWN_HOSTS, CONF_KNOWN_HOSTS


async def _validate_service_data(data: dict[str, Any]) -> None:
    has_username: bool = bool(data.get(CONF_USERNAME))
    has_password: bool = bool(data.get(CONF_PASSWORD))

    # Username and password must be provided together
    if has_username != has_password:
        raise ServiceValidationError(
            "When providing a username, also provide a password and vice versa.",
            translation_domain=DOMAIN,
            translation_key="username_password_both_required",
        )

    # from here, we know that username and password are either both provided or both absent

    has_key_file: bool = bool(data.get(CONF_KEY_FILE))

    if not has_username and not has_key_file:
        raise ServiceValidationError(
            "Either username/password or key file must be provided.",
            translation_domain=DOMAIN,
            translation_key="username_password_or_key_file",
        )

    has_command: bool = bool(data.get(CONF_COMMAND))
    has_script_file: bool = bool(data.get(CONF_SCRIPT_FILE))

    if not has_command and not has_script_file:
        raise ServiceValidationError(
            "Either command or script file must be provided.",
            translation_domain=DOMAIN,
            translation_key="command_or_script_file",
        )

    if has_key_file and not await exists(data[CONF_KEY_FILE]):
        raise ServiceValidationError(
            "Could not find key file.",
            translation_domain=DOMAIN,
            translation_key="key_file_not_found",
        )

    if has_script_file and not await exists(data[CONF_SCRIPT_FILE]):
        raise ServiceValidationError(
            "Could not find script file.",
            translation_domain=DOMAIN,
            translation_key="script_file_not_found",
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
            vol.Optional(CONF_USERNAME): str,
            vol.Optional(CONF_PASSWORD): str,
            vol.Optional(CONF_KEY_FILE): str,
            vol.Optional(CONF_COMMAND): str,
            vol.Optional(CONF_SCRIPT_FILE): str,
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
        script_file = service_call.data.get(CONF_SCRIPT_FILE)
        check_known_hosts = service_call.data.get(CONF_CHECK_KNOWN_HOSTS, True)
        known_hosts = service_call.data.get(CONF_KNOWN_HOSTS)
        timeout = service_call.data.get(CONF_TIMEOUT, CONST_DEFAULT_TIMEOUT)

        key_file_content = []
        if key_file:
            async with aioopen(key_file, 'r') as kf:
                key_file_content = [await kf.read()]

        script_file_content = None
        if script_file:
            async with aioopen(script_file, 'r') as sf:
                script_file_content = await sf.read()

        conn_kwargs = {
            "host": host,
            "username": username,
            "password": password,
            "client_keys": key_file_content,
        }

        if check_known_hosts:
            if not known_hosts:
                known_hosts = (Path.home() / '.ssh' / 'known_hosts').as_posix()
            if await exists(known_hosts):
                # open the known hosts file asynchronously, otherwise Home Assistant will complain about blocking I/O
                conn_kwargs["known_hosts"] = await hass.async_add_executor_job(read_known_hosts, known_hosts)
            else:
                conn_kwargs["known_hosts"] = known_hosts
        else:
            conn_kwargs["known_hosts"] = None

        run_kwargs = {
            "command": command,
            "check": False,
            "timeout": timeout,
        }

        if script_file_content:
            run_kwargs["input"] = script_file_content

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
        except OSError:
            raise ServiceValidationError(
                "Host is not reachable.",
                translation_domain=DOMAIN,
                translation_key="host_not_reachable",
            )

        return {
            "output": result.stdout,
            "error": result.stderr,
            "exit_status": result.exit_status,
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
