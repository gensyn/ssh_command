import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

absolute_plugin_path = str(Path(__file__).parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_command import async_setup, async_setup_entry, async_unload_entry
from ssh_command.const import DOMAIN, SERVICE_EXECUTE


class TestAsyncSetup(unittest.IsolatedAsyncioTestCase):

    async def test_registers_service_and_returns_true(self):
        mock_hass = MagicMock()

        result = await async_setup(mock_hass, {})

        self.assertTrue(result)
        mock_hass.services.async_register.assert_called_once()
        call_args = mock_hass.services.async_register.call_args[0]
        self.assertEqual(call_args[0], DOMAIN)
        self.assertEqual(call_args[1], SERVICE_EXECUTE)


class TestAsyncSetupEntry(unittest.IsolatedAsyncioTestCase):

    async def test_returns_true(self):
        mock_hass = MagicMock()
        mock_entry = MagicMock()

        result = await async_setup_entry(mock_hass, mock_entry)

        self.assertTrue(result)


class TestAsyncUnloadEntry(unittest.IsolatedAsyncioTestCase):

    async def test_returns_true(self):
        mock_hass = MagicMock()
        mock_entry = MagicMock()

        result = await async_unload_entry(mock_hass, mock_entry)

        self.assertTrue(result)
