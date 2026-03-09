import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

absolute_plugin_path = str(Path(__file__).parent.parent.parent.absolute())
sys.path.insert(0, absolute_plugin_path)

from ssh_command.config_flow import SshCommandConfigFlow
from ssh_command.const import DOMAIN


class TestConfigFlowAsyncStepUser(unittest.IsolatedAsyncioTestCase):

    def _make_flow(self, existing_entries=None):
        mock_hass = MagicMock()
        mock_hass.data = {}
        flow = SshCommandConfigFlow()
        flow.hass = mock_hass
        flow.context = {"source": "user"}
        entries = existing_entries if existing_entries is not None else []
        flow._async_current_entries = lambda: entries
        return flow

    async def test_creates_entry_on_first_setup(self):
        flow = self._make_flow()

        result = await flow.async_step_user()

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "SSH Command")
        self.assertEqual(result["data"], {})

    async def test_aborts_when_entry_already_exists(self):
        flow = self._make_flow(existing_entries=[MagicMock()])

        result = await flow.async_step_user()

        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "single_instance_allowed")

    async def test_aborts_when_domain_in_hass_data(self):
        flow = self._make_flow()
        flow.hass.data[DOMAIN] = object()

        result = await flow.async_step_user()

        self.assertEqual(result["type"], "abort")
        self.assertEqual(result["reason"], "single_instance_allowed")
