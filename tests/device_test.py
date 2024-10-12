"""Test cases for the Device class."""

import asyncio
from unittest.mock import MagicMock
import pytest
from device import Device


@pytest.fixture
def device():
    """Fixture for creating a Device instance with a mocked Arlo device."""
    arlo_device = MagicMock()
    status_interval = 10
    return Device(arlo_device, status_interval)


@pytest.mark.asyncio
class TestDevice:
    """Test suite for the Device class."""

    @pytest.mark.asyncio
    async def test_run(self, device):
        """Test the run method."""

        event_get, event_put = self.create_sync_async_channel()
        self._arlo.add_attr_callback("*", event_put)
        asyncio.create_task(self.periodic_status_trigger())

        async for device, attr, value in event_get:
            if device == self._arlo:
                asyncio.create_task(self.on_event(attr, value))

    async def test_on_event(self, device):
        """Test the on_event method."""
        pass

    async def test_periodic_status_trigger(self, device):
        """Test the periodic_status_trigger method."""
        pass

    async def test_listen_status(self, device):
        """Test the listen_status method."""
        pass

    def test_get_status(self, device):
        """Test the get_status method."""
        pass

    async def test_mqtt_control(self, device):
        """Test the mqtt_control method."""
        pass
