import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import logging
import warnings
# import tracemalloc
import pytest
from pytest_mock import MockerFixture
from camera import Camera

warnings.filterwarnings("error", category=RuntimeWarning)

# tracemalloc.start()


class AsyncMockSubprocess:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.communicate = AsyncMock(return_value=("output", "error"))
        self.wait = AsyncMock(return_value=0)
        self.kill = MagicMock()
        self.terminate = MagicMock()
        self.stdin = MagicMock()
        self.stdout = MagicMock()
        self.stderr = AsyncMock()
        self.stderr.readline = AsyncMock(side_effect=[b"error message\n", b""])


class MockSubprocess:
    def __init__(self, *args, **kwargs):
        self.terminate = MagicMock()


class TestCamera:
    @pytest.fixture
    def mock_arlo_camera(self):
        return MagicMock(is_unavailable=False, battery_level=50)

    @pytest.fixture
    def camera(self, mock_arlo_camera, event_loop):
        with patch("asyncio.get_running_loop", return_value=event_loop):
            camera = Camera(mock_arlo_camera, "ffmpeg -i pipe: -f null -", 10, 30)
            camera.event_loop = event_loop
            return camera

    @pytest.mark.asyncio
    async def test_camera_start_proxy_stream(self, camera, mocker: MockerFixture):
        mock_subprocess = AsyncMockSubprocess()
        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_subprocess
        ) as mock_create_subprocess:
            await camera._start_proxy_stream()
            mock_create_subprocess.assert_called_once()
            assert camera.proxy_stream == mock_subprocess

    @pytest.mark.asyncio
    async def test_camera_start_idle_stream(self, camera, mocker: MockerFixture):
        mock_subprocess = AsyncMockSubprocess()
        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_subprocess
        ) as mock_create_subprocess:
            await camera._start_idle_stream()
            mock_create_subprocess.assert_called_once()
            assert camera.stream == mock_subprocess

    @pytest.mark.asyncio
    async def test_camera_start_stream(self, camera, mocker: MockerFixture):
        mock_subprocess = AsyncMockSubprocess()
        with (
            patch.object(
                camera._arlo,
                "get_stream",
                new_callable=AsyncMock,
                return_value="stream_url",
            ) as mock_get_stream,
            patch.object(Camera, "stop_stream") as mock_stop_stream,
            patch(
                "asyncio.create_subprocess_exec", return_value=mock_subprocess
            ) as mock_create_subprocess,
        ):
            await camera._start_stream()
            mock_get_stream.assert_called_once()
            mock_stop_stream.assert_called_once()
            mock_create_subprocess.assert_called_once()
            assert camera.stream == mock_subprocess

    @pytest.mark.asyncio
    async def test_camera_get_pictures(self, camera):
        test_data = ["picture_data_1", "picture_data_2"]
        get_mock = AsyncMock(side_effect=test_data + [asyncio.CancelledError])
        camera._pictures.get = get_mock
        camera._pictures.task_done = MagicMock()

        results = []
        get_pictures_gen = camera.get_pictures()
        try:
            async for name, data in get_pictures_gen:
                results.append((name, data))
        except asyncio.CancelledError:
            pass

        assert results == [(camera.name, data) for data in test_data]
        assert camera._listen_pictures is True
        assert camera._pictures.task_done.call_count == 2
        assert get_mock.await_count == 3

    @pytest.mark.asyncio
    async def test_camera_listen_motion(self, camera):
        camera.motion = True
        camera._motion_event = AsyncMock()
        camera._motion_event.wait = AsyncMock()
        camera._motion_event.clear = MagicMock()

        results = []
        async for name, motion in camera.listen_motion():
            results.append((name, motion))
            if len(results) == 1:
                break

        assert results == [(camera.name, True)]
        camera._motion_event.wait.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_camera_log_stderr(self, camera, caplog):
        caplog.set_level(logging.DEBUG)
        mock_stream = AsyncMockSubprocess()
        await camera._log_stderr(mock_stream, "test_label")
        assert "test_label: error message" in caplog.text

    @pytest.mark.asyncio
    async def test_camera_shutdown_when_idle(self, camera):
        with (
            patch.object(
                Camera, "get_state", side_effect=["streaming", "streaming", "idle"]
            ),
            patch.object(Camera, "shutdown") as mock_shutdown,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await camera.shutdown_when_idle()
            mock_sleep.assert_awaited()
            mock_shutdown.assert_called_once()

    @pytest.fixture
    def test_camera_shutdown(self, camera, caplog):
        caplog.set_level(logging.INFO)
        camera.stream = MockSubprocess()
        camera.proxy_stream = MockSubprocess()

        camera.shutdown()

        assert f"Shutting down {camera.name}" in caplog.text
        camera.stream.terminate.assert_called_once()
        camera.proxy_stream.terminate.assert_called_once()

    @pytest.fixture
    def test_camera_shutdown_with_exceptions(self, camera, caplog):
        caplog.set_level(logging.DEBUG)
        camera.stream = MockSubprocess()
        camera.stream.terminate.side_effect = ProcessLookupError
        camera.proxy_stream = None

        camera.shutdown()

        assert f"Shutting down {camera.name}" in caplog.text
        assert f"Process for {camera.name} already terminated." in caplog.text
        assert f"Stream for {camera.name} is not initialized." in caplog.text
        camera.stream.terminate.assert_called_once()
