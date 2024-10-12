"""Test cases for the Base class."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from base import Base
from device import Device


@pytest.fixture
def base(mocker):
    """Fixture for creating a Base instance with a mocked Arlo base."""
    arlo_base = mocker.MagicMock()
    status_interval = 10

    # Create a new event loop
    event_loop = asyncio.new_event_loop()

    # Patch the _event_loop attribute on the Device class with the new event loop
    mocker.patch.object(Device, "_event_loop", new=event_loop)

    base_instance = Base(arlo_base, status_interval)

    return base_instance


@pytest.mark.asyncio
class TestBase(TestDevice):
    """Test suite for the Base class."""

    @pytest.mark.parametrize(
        "attr,value",
        [
            ("activeMode", "mode1"),
            ("otherAttr", "value"),
        ],
    )
    async def test_on_event(self, base, mocker, attr, value):
        """Test the on_event method."""
        # Patch the state_event property with a mock object
        mock_state_event = mocker.patch.object(
            base, "state_event", new_callable=AsyncMock
        )

        # Call the on_event method with the provided attr and value
        await base.on_event(attr, value)

        # Assertions for the "activeMode" case
        if attr == "activeMode":
            mock_state_event.set.assert_called_once()
            assert base._arlo.mode == value

        # Assertions for other cases
        else:
            mock_state_event.set.assert_not_called()

    # def test_get_status(self, base):
    #     """Test the get_status method."""
    #     pass

    # async def test_mqtt_control(self, base):
    #     """Test the mqtt_control method."""
    #     pass

    # def test_set_mode(self, base):
    #     """Test the set_mode method."""
    #     pass

    # def test_set_siren(self, base):
    #     """Test the set_siren method."""
    #     pass
