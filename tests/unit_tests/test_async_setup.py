import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

absolute_mock_path = str(Path(__file__).parent / "homeassistant_mock")
sys.path.insert(0, absolute_mock_path)

absolute_plugin_path = str(Path(__file__).parent.parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_command import async_setup, async_setup_entry, async_unload_entry
from ssh_command.const import DOMAIN, SERVICE_EXECUTE
from ssh_command.coordinator import SshCommandCoordinator


class TestAsyncSetup(unittest.IsolatedAsyncioTestCase):

    async def test_registers_service_and_returns_true(self):
        mock_hass = MagicMock()
        mock_hass.data = {}

        result = await async_setup(mock_hass, {})

        self.assertTrue(result)
        mock_hass.services.async_register.assert_called_once()
        call_args = mock_hass.services.async_register.call_args[0]
        self.assertEqual(call_args[0], DOMAIN)
        self.assertEqual(call_args[1], SERVICE_EXECUTE)


class TestAsyncSetupEntry(unittest.IsolatedAsyncioTestCase):

    async def test_returns_true(self):
        mock_hass = MagicMock()
        mock_hass.data = {}
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"

        result = await async_setup_entry(mock_hass, mock_entry)

        self.assertTrue(result)

    async def test_creates_coordinator_in_hass_data(self):
        mock_hass = MagicMock()
        mock_hass.data = {}
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"

        await async_setup_entry(mock_hass, mock_entry)

        self.assertIn(DOMAIN, mock_hass.data)
        self.assertIn("test_entry", mock_hass.data[DOMAIN])
        self.assertIsInstance(mock_hass.data[DOMAIN]["test_entry"], SshCommandCoordinator)

    async def test_coordinator_holds_hass_reference(self):
        mock_hass = MagicMock()
        mock_hass.data = {}
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"

        await async_setup_entry(mock_hass, mock_entry)

        coordinator = mock_hass.data[DOMAIN]["test_entry"]
        self.assertIs(coordinator.hass, mock_hass)


class TestAsyncUnloadEntry(unittest.IsolatedAsyncioTestCase):

    async def test_returns_true(self):
        mock_hass = MagicMock()
        mock_hass.data = {}
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"

        result = await async_unload_entry(mock_hass, mock_entry)

        self.assertTrue(result)

    async def test_removes_coordinator_from_hass_data(self):
        mock_hass = MagicMock()
        mock_hass.data = {}
        mock_entry = MagicMock()
        mock_entry.entry_id = "test_entry"

        await async_setup_entry(mock_hass, mock_entry)
        self.assertIn("test_entry", mock_hass.data[DOMAIN])

        await async_unload_entry(mock_hass, mock_entry)

        self.assertNotIn("test_entry", mock_hass.data[DOMAIN])
