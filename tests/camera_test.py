"""Test cases for the Camera class."""

import asyncio
from unittest.mock import MagicMock
import pytest
from camera import Camera


@pytest.fixture
def camera():
    """Fixture for creating a Camera instance with a mocked Arlo camera."""
    arlo_camera = MagicMock()
    ffmpeg_out = "test_ffmpeg_out"
    motion_timeout = 30
    status_interval = 10
    return Camera(arlo_camera, ffmpeg_out, motion_timeout, status_interval)


@pytest.mark.asyncio
class TestCamera:
    """Test suite for the Camera class."""

    async def test_run(self, camera):
        """Test the run method."""
        pass

    async def test_on_motion(self, camera):
        """Test the on_motion method."""
        pass

    async def test_on_arlo_state(self, camera):
        """Test the on_arlo_state method."""
        pass

    async def test_set_state(self, camera):
        """Test the set_state method."""
        pass

    async def test_start_stream(self, camera):
        """Test the start_stream method."""
        pass

    async def test_stream_timeout(self, camera):
        """Test the stream_timeout method."""
        pass

    def test_stop_stream(self, camera):
        """Test the stop_stream method."""
        pass

    async def test_get_pictures(self, camera):
        """Test the get_pictures method."""
        pass

    def test_put_picture(self, camera):
        """Test the put_picture method."""
        pass

    def test_get_status(self, camera):
        """Test the get_status method."""
        pass

    async def test_listen_motion(self, camera):
        """Test the listen_motion method."""
        pass

    async def test_mqtt_control(self, camera):
        """Test the mqtt_control method."""
        pass

    async def test_shutdown_when_idle(self, camera):
        """Test the shutdown_when_idle method."""
        pass

    def test_shutdown(self, camera):
        """Test the shutdown method."""
        pass
