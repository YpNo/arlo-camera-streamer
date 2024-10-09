import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json
import base64
import warnings
# import tracemalloc
import pytest

# Import the functions to be tested
from mqtt import mqtt_client, pic_streamer, device_status, motion_stream, mqtt_reader

warnings.filterwarnings("error", category=RuntimeWarning)

class AsyncIteratorMock:
    def __init__(self, seq):
        self.iter = iter(seq)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

class AsyncContextManagerMock:
    def __init__(self, mock_obj):
        self.mock_obj = mock_obj

    async def __aenter__(self):
        return self.mock_obj

    async def __aexit__(self, exc_type, exc, tb):
        pass

@pytest.fixture
def mock_client():
    client = AsyncMock()
    messages_context = AsyncContextManagerMock(AsyncIteratorMock([]))
    client.messages = MagicMock(return_value=messages_context)
    client.publish = AsyncMock()
    return client

@pytest.fixture
def mock_camera():
    camera = MagicMock()
    camera.name = "test_camera"
    camera.get_pictures = MagicMock(return_value=AsyncIteratorMock([("test_camera", b"test_image_data")]))
    camera.listen_status = MagicMock(return_value=AsyncIteratorMock([("test_camera", {"status": "online"})]))
    camera.listen_motion = MagicMock(return_value=AsyncIteratorMock([("test_camera", {"motion": True})]))
    
    async def mock_mqtt_control(arg):
        # This function will be called with the actual argument
        return arg
    camera.mqtt_control = AsyncMock(side_effect=mock_mqtt_control)
    
    return camera

@pytest.mark.asyncio
async def test_pic_streamer(mock_client, mock_camera):
    await pic_streamer(mock_client, [mock_camera])
    mock_client.publish.assert_called_once()
    call_args = mock_client.publish.call_args
    assert call_args is not None
    args, kwargs = call_args
    assert len(args) >= 1, "Expected at least one positional argument"
    topic = args[0]
    payload = kwargs.get('payload') or (args[1] if len(args) > 1 else None)
    assert topic == "arlo/picture/test_camera"
    assert payload is not None
    payload_data = json.loads(payload)
    assert "filename" in payload_data
    assert "payload" in payload_data
    assert base64.b64decode(payload_data["payload"]) == b"test_image_data"

@pytest.mark.asyncio
async def test_device_status(mock_client, mock_camera):
    await device_status(mock_client, [mock_camera])
    mock_client.publish.assert_called_once_with(
        "arlo/status/test_camera",
        payload='{"status": "online"}'
    )

@pytest.mark.asyncio
async def test_motion_stream(mock_client, mock_camera):
    await motion_stream(mock_client, [mock_camera])
    mock_client.publish.assert_called_once_with(
        "arlo/motion/test_camera",
        payload='{"motion": true}'
    )

@pytest.mark.asyncio
async def test_mqtt_reader(mock_client, mock_camera):
    mock_message = AsyncMock()
    mock_message.topic.value = "arlo/control/test_camera"
    mock_message.payload.decode.return_value = '{"command": "take_picture"}'
    
    mock_client.messages.return_value = AsyncContextManagerMock(AsyncIteratorMock([mock_message]))
    
    # Make mqtt_control return a coroutine
    async def mock_mqtt_control(arg):
        # Here we can check the arg if needed
        assert arg == '{"command": "take_picture"}'
    mock_camera.mqtt_control = AsyncMock(side_effect=mock_mqtt_control)
    
    await mqtt_reader(mock_client, [mock_camera])
    
    mock_client.subscribe.assert_called_once_with("arlo/control/test_camera")
    mock_camera.mqtt_control.assert_called_once()
    
    # Check that the coroutine was called
    call_args = mock_camera.mqtt_control.call_args
    assert call_args is not None
    args, _ = call_args
    
    # Await the coroutine argument to get its value
    arg_value = await args[0]
    assert arg_value == '{"command": "take_picture"}'

@pytest.mark.asyncio
async def test_mqtt_client():
    mock_camera = AsyncMock()
    mock_base = AsyncMock()
    
    with patch('mqtt.aiomqtt.Client') as mock_aiomqtt_client, \
         patch('mqtt.asyncio.gather') as mock_gather, \
         patch('mqtt.asyncio.sleep') as mock_sleep:
        
        mock_client_context = AsyncMock()
        mock_aiomqtt_client.return_value.__aenter__.return_value = mock_client_context
        
        # Create a Future that never completes to simulate the continuous loop
        never_ending_future = asyncio.Future()
        mock_gather.return_value = never_ending_future
        
        # Run the client for a short time
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(mqtt_client([mock_camera], [mock_base]), timeout=0.1)
        
        assert mock_aiomqtt_client.call_count == 1
        assert mock_gather.call_count == 1
        assert mock_sleep.call_count == 0  # No reconnection attempts in this short run

if __name__ == "__main__":
    pytest.main()