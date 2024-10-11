"""Device Class to manage Arlo's Camera devices."""

import asyncio


class Device:
    """
    Base class for Arlo devices (cameras and base stations).

    Attributes:
        name (str): Internal name of the device (not necessarily identical to Arlo).
        status_interval (int): Interval of status messages from generator (seconds).
    """

    def __init__(self, arlo_device, status_interval):
        """
        Initialize the Device instance.

        Args:
            arlo_device (ArloDevice): Arlo device object.
            status_interval (int): Interval of status messages from generator (seconds).
        """
        self._arlo = arlo_device
        self.name = self._arlo.name.replace(" ", "_").lower()
        self.status_interval = status_interval
        self._state_event = asyncio.Event()
        self.event_loop = asyncio.get_running_loop()

    async def run(self):
        """
        Initialize the device, create event channels, and listen for events.

        This method performs the following tasks:
        - Creates an event channel between pyaarlo callbacks and async generator.
        - Adds a callback to the Arlo device for all attributes.
        - Starts periodic status trigger.
        - Listens for and passes events to the handler.
        """

        event_get, event_put = self.create_sync_async_channel()
        self._arlo.add_attr_callback("*", event_put)
        asyncio.create_task(self._periodic_status_trigger())

        async for device, attr, value in event_get:
            if device == self._arlo:
                asyncio.create_task(self.on_event(attr, value))

    async def on_event(self, attr, value):
        """
        Distribute events to the correct handler.

        This method should be overridden by subclasses to handle specific events.

        Args:
            attr (str): Attribute name.
            value: Attribute value.
        """
        pass  # pylint: disable=unnecessary-pass

    async def _periodic_status_trigger(self):
        """Periodically trigger status updates."""
        while True:
            self._state_event.set()
            await asyncio.sleep(self.status_interval)

    async def listen_status(self):
        """
        Async generator that periodically yields status messages for MQTT.

        Yields:
            tuple: (name, status) where name is the device name and status is the device status.
        """
        while True:
            await self._state_event.wait()
            status = self.get_status()
            yield self.name, status
            self._state_event.clear()

    def get_status(self) -> dict:
        """
        Get the device status.

        This method should be overridden by subclasses to provide device-specific status.

        Returns:
            dict: Device status information.
        """
        return {}

    async def mqtt_control(self, payload):
        """
        Handle MQTT control messages.

        This method should be overridden by subclasses to handle device-specific MQTT controls.

        Args:
            payload (str): MQTT payload.
        """
        pass  # pylint: disable=unnecessary-pass

    def create_sync_async_channel(self):
        """
        Create a synchronous/asynchronous channel for event communication.

        Returns:
            tuple: (get, put) where get is an async generator that yields queued data,
                and put is a function used in synchronous callbacks to put data into the queue.
        """
        queue = asyncio.Queue()

        def put(*args):
            self.event_loop.call_soon_threadsafe(queue.put_nowait, args)

        async def get():
            while True:
                yield await queue.get()
                queue.task_done()

        return get(), put
