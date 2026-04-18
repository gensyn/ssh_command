"""Coordinator for the SSH Command integration.

The SshCommandCoordinator is the single owner of all SSH I/O for the
integration.  It encapsulates connection management and command execution
so that the service handler in __init__.py is a pure dispatcher.

Preferred HA pattern: coordinator (or "client") owns I/O; the service
handler validates input and delegates to this class.
"""

from __future__ import annotations

import logging
import socket
import sys
from pathlib import Path
from typing import Any

# asyncssh optionally imports fido2.client.windows for Windows WebAuthn support.
# fido2's Windows-specific module (win_api) uses ctypes.HRESULT, which Python 3.14
# removed on non-Windows platforms, causing an AttributeError that asyncssh does not
# catch (it only catches ImportError in that code path).  Pre-attempt the import here
# so that on failure we can replace the broken sys.modules entry with None, which
# makes Python raise ImportError instead — and asyncssh handles that gracefully.
if sys.platform != "win32":
    try:
        import fido2.client.windows  # noqa: F401
    except (ImportError, OSError, AttributeError):
        sys.modules["fido2.client.windows"] = None  # type: ignore[assignment]

from asyncssh import HostKeyNotVerifiable, KeyImportError, PermissionDenied, connect, read_known_hosts

from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_HOST, CONF_COMMAND, CONF_TIMEOUT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .const import (
    DOMAIN,
    CONF_KEY_FILE,
    CONF_INPUT,
    CONF_CHECK_KNOWN_HOSTS,
    CONF_KNOWN_HOSTS,
    CONF_CLIENT_KEYS,
    CONF_CHECK,
    CONF_OUTPUT,
    CONF_ERROR,
    CONF_EXIT_STATUS,
    CONST_DEFAULT_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class SshCommandCoordinator:
    """Single owner of all SSH I/O for the SSH Command integration.

    Preferred HA pattern: coordinator owns I/O; the service handler in
    __init__.py validates input and delegates execution to this class.
    """

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the coordinator."""
        self.hass = hass

    async def async_execute(self, data: dict[str, Any]) -> dict[str, Any]:
        """Execute an SSH command and return stdout, stderr and exit status."""
        host = data.get(CONF_HOST)
        username = data.get(CONF_USERNAME)
        password = data.get(CONF_PASSWORD)
        key_file = data.get(CONF_KEY_FILE)
        command = data.get(CONF_COMMAND)
        input_data = data.get(CONF_INPUT)
        check_known_hosts = data.get(CONF_CHECK_KNOWN_HOSTS, True)
        known_hosts = data.get(CONF_KNOWN_HOSTS)
        timeout = data.get(CONF_TIMEOUT, CONST_DEFAULT_TIMEOUT)

        if input_data:
            if await self.hass.async_add_executor_job(Path(input_data).exists):
                input_data = await self.hass.async_add_executor_job(Path(input_data).read_text)

        conn_kwargs = {
            CONF_HOST: host,
            CONF_USERNAME: username,
            CONF_PASSWORD: password,
            CONF_CLIENT_KEYS: key_file,
            CONF_KNOWN_HOSTS: await self._resolve_known_hosts(check_known_hosts, known_hosts),
            "connect_timeout": timeout,
        }

        run_kwargs: dict[str, Any] = {
            CONF_COMMAND: command,
            CONF_CHECK: False,
            CONF_TIMEOUT: timeout,
        }

        if input_data:
            run_kwargs[CONF_INPUT] = input_data

        try:
            async with connect(**conn_kwargs) as conn:
                result = await conn.run(**run_kwargs)
        except HostKeyNotVerifiable as exc:
            _LOGGER.warning("Host key not verifiable for %s: %s", host, exc)
            raise ServiceValidationError(
                "The host key could not be verified.",
                translation_domain=DOMAIN,
                translation_key="host_key_not_verifiable",
            ) from exc
        except KeyImportError as exc:
            _LOGGER.warning("Invalid key file for %s@%s: %s", username, host, exc)
            raise ServiceValidationError(
                "The key file is not a valid private key.",
                translation_domain=DOMAIN,
                translation_key="invalid_key_file",
            ) from exc
        except PermissionDenied as exc:
            _LOGGER.warning("SSH login failed for %s@%s: %s", username, host, exc)
            raise ServiceValidationError(
                "SSH login failed.",
                translation_domain=DOMAIN,
                translation_key="login_failed",
            ) from exc
        except TimeoutError as exc:
            _LOGGER.warning("SSH connection to %s timed out: %s", host, exc)
            raise ServiceValidationError(
                "Connection timed out.",
                translation_domain=DOMAIN,
                translation_key="connection_timed_out",
            ) from exc
        except OSError as exc:
            if isinstance(exc, socket.gaierror):
                _LOGGER.warning("Host %s is not reachable: %s", host, exc)
                raise ServiceValidationError(
                    "Host is not reachable.",
                    translation_domain=DOMAIN,
                    translation_key="host_not_reachable",
                ) from exc
            raise

        return {
            CONF_OUTPUT: result.stdout,
            CONF_ERROR: result.stderr,
            CONF_EXIT_STATUS: result.exit_status,
        }

    async def _resolve_known_hosts(self, check_known_hosts: bool, known_hosts: str | None) -> str | None:
        """Resolve the known_hosts value for the SSH connection."""
        if not check_known_hosts:
            return None
        if not known_hosts:
            known_hosts = str(Path("~", ".ssh", "known_hosts").expanduser())
        if await self.hass.async_add_executor_job(Path(known_hosts).exists):
            return await self.hass.async_add_executor_job(read_known_hosts, known_hosts)
        return known_hosts
