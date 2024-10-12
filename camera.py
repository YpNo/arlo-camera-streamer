"""Camera Class to manage Arlo's Camera devices."""

import subprocess  # nosec B404
import logging
import asyncio
import shlex
import os
from decouple import config
from device import Device

DEBUG = config("DEBUG", default=False, cast=bool)

# Initialize logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class Camera(Device):
    """
    Class representing an Arlo camera device.

    Attributes:
        name (str): Internal name of the camera (not necessarily identical to Arlo).
        ffmpeg_out (str): FFmpeg output string.
        timeout (int): Motion timeout of live stream (seconds).
        status_interval (int): Interval of status messages from generator (seconds).
        stream (asyncio.subprocess.Process): Current FFmpeg stream (idle or active).
    """

    # pylint: disable=too-many-instance-attributes
    # pylint: disable=too-many-public-methods

    # Possible states
    STATES = ["idle", "streaming"]

    def __init__(
        self, arlo_camera, ffmpeg_out: str, motion_timeout: int, status_interval: int
    ):
        """
        Initialize the Camera instance.

        Args:
            arlo_camera (ArloCamera): Arlo camera object.
            ffmpeg_out (str): FFmpeg output string.
            motion_timeout (int): Motion timeout of live stream (seconds).
            status_interval (int): Interval of status messages from generator (seconds).
        """
        super().__init__(arlo_camera, status_interval)
        self.name = arlo_camera.name.replace(" ", "_").lower()
        self.ffmpeg_out = shlex.split(ffmpeg_out.format(name=self.name))
        self.timeout = motion_timeout
        self._timeout_task = None
        self.motion = False
        self._state = None
        self._motion_event = asyncio.Event()
        self.stream = None
        self.proxy_stream = None
        self.proxy_reader, self.proxy_writer = os.pipe()
        self._pictures = asyncio.Queue()
        self._listen_pictures = False
        logger.info("Camera added: %s", self.name)

    async def run(self):
        """
        Start the camera, wait for it to become available, create event channels,
        and listen for events.
        """
        while self._arlo.is_unavailable:
            await asyncio.sleep(5)
        await self.set_state("idle")
        asyncio.create_task(self.start_proxy_stream())
        await super().run()

    async def on_event(self, attr: str, value):
        """
        Distribute events to the correct handler.

        Args:
            attr (str): Attribute name.
            value: Attribute value.
        """
        match attr:
            case "motionDetected":
                await self.on_motion(value)
            case "activityState":
                await self.on_arlo_state(value)
            case "presignedLastImageData":
                if self._listen_pictures:
                    self.put_picture(value)
            case _:
                pass

    async def on_motion(self, motion: bool):
        """
        Handle motion events. Either start live stream or reset live stream timeout.

        Args:
            motion (bool): Motion detected status.
        """
        self.motion = motion
        self.motion_event.set()
        logger.info("%s motion: %s", self.name, motion)
        if motion:
            await self.set_state("streaming")
        else:
            if self._timeout_task:
                self._timeout_task.cancel()
            if not motion:
                self._timeout_task = asyncio.create_task(self.stream_timeout())

    async def on_arlo_state(self, state: str):
        """
        Handle pyaarlo state change, either request stream or handle running stream.

        Args:
            state (str): Arlo state.
        """
        if state == "idle":
            if self.get_state() == "streaming":
                await self.start_stream()
        elif state == "userStreamActive" and self.get_state() != "streaming":
            await self.set_state("streaming")

    async def set_state(self, new_state: str):
        """
        Set the local state when pyaarlo state changes.
        Call the _on_state_change function if the state has changed.

        Args:
            new_state (str): New state.
        """
        if new_state in self.STATES and new_state != self._state:
            self._state = new_state
            logger.info("%s state: %s", self.name, new_state)
            await self.on_state_change(new_state)

    def get_state(self):
        """
        Get the current state.

        Returns:
            str: Current state.
        """
        return self._state

    async def on_state_change(self, new_state: str):
        """
        Handle internal state change, stop or start stream.

        Args:
            new_state (str): New state.
        """
        self.state_event.set()
        match new_state:
            case "idle":
                self.stop_stream()
                asyncio.create_task(self.start_idle_stream())
            case "streaming":
                await self.start_stream()

    async def start_proxy_stream(self):
        """Start the proxy stream (continuous video stream from FFmpeg)."""
        exit_code = 1
        while exit_code > 0:
            self.proxy_stream = await asyncio.create_subprocess_exec(
                *(["ffmpeg", "-i", "pipe:"] + self.ffmpeg_out),
                stdin=self.proxy_reader,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE if DEBUG else subprocess.DEVNULL,
            )

            if DEBUG:
                asyncio.create_task(self.log_stderr(self.proxy_stream, "proxy_stream"))

            exit_code = await self.proxy_stream.wait()

            if exit_code > 0:
                logger.warning(
                    "Proxy stream for %s exited unexpectedly with code %s. Restarting...",
                    self.name,
                    exit_code,
                )
                await asyncio.sleep(3)

    async def start_idle_stream(self):
        """Start the idle picture stream, writing to the proxy stream."""
        exit_code = 1
        while exit_code > 0:
            self.stream = await asyncio.create_subprocess_exec(
                *[
                    "ffmpeg",
                    "-re",
                    "-stream_loop",
                    "-1",
                    "-i",
                    "idle.mp4",
                    "-c:v",
                    "copy",
                    "-c:a",
                    "libmp3lame",
                    "-ar",
                    "44100",
                    "-b:a",
                    "8k",
                    "-bsf",
                    "dump_extra",
                    "-f",
                    "mpegts",
                    "pipe:",
                ],
                stdin=subprocess.DEVNULL,
                stdout=self.proxy_writer,
                stderr=subprocess.PIPE if DEBUG else subprocess.DEVNULL,
            )

            if DEBUG:
                asyncio.create_task(self.log_stderr(self.stream, "idle_stream"))

            exit_code = await self.stream.wait()

            if exit_code > 0:
                logger.warning(
                    "Idle stream for %s exited unexpectedly with code %s. Restarting...",
                    self.name,
                    exit_code,
                )
                await asyncio.sleep(3)

    async def start_stream(self):
        """
        Request stream, grab it, kill idle stream, and start a new FFmpeg instance
        writing to the proxy stream.
        """
        stream = await self.event_loop.run_in_executor(None, self._arlo.get_stream)
        if stream:
            self.stop_stream()

            self.stream = await asyncio.create_subprocess_exec(
                *[
                    "ffmpeg",
                    "-i",
                    stream,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "libmp3lame",
                    "-ar",
                    "44100",
                    "-bsf",
                    "dump_extra",
                    "-f",
                    "mpegts",
                    "pipe:",
                ],
                stdin=subprocess.DEVNULL,
                stdout=self.proxy_writer,
                stderr=subprocess.PIPE if DEBUG else subprocess.DEVNULL,
            )

            if DEBUG:
                asyncio.create_task(self.log_stderr(self.stream, "live_stream"))

    async def stream_timeout(self):
        """Timeout the live stream after the specified duration."""
        await asyncio.sleep(self.timeout)
        await self.set_state("idle")

    def stop_stream(self):
        """Stop the live or idle stream (not the proxy stream)."""
        if self.stream:
            try:
                self.stream.kill()
            except ProcessLookupError:
                pass

    async def get_pictures(self):
        """
        Async generator that yields snapshots from pyaarlo.

        Yields:
            tuple: (name, data) where name is the camera name and data is the picture data.
        """
        self._listen_pictures = True
        while True:
            data = await self._pictures.get()
            yield self.name, data
            self._pictures.task_done()

    def put_picture(self, pic):
        """
        Put a picture into the queue.

        Args:
            pic: Picture data.
        """
        try:
            self._pictures.put_nowait(pic)
        except asyncio.QueueFull:
            logger.info("picture queue full, ignoring")

    def get_status(self) -> dict:
        """
        Get the camera status information.

        Returns:
            dict: Camera status information.
        """
        return {"battery": self._arlo.battery_level, "state": self.get_state()}

    async def listen_motion(self):
        """
        Async generator that yields motion state on change.

        Yields:
            tuple: (name, motion) where name is the camera name and motion is the motion state.
        """
        while True:
            await self.motion_event.wait()
            yield self.name, self.motion
            self.motion_event.clear()

    async def mqtt_control(self, payload: str):
        """
        Handle incoming MQTT commands.

        Args:
            payload (str): MQTT payload.
        """
        match payload.upper():
            case "START":
                await self.set_state("streaming")
            case "STOP":
                await self.set_state("idle")
            case "SNAPSHOT":
                await self.event_loop.run_in_executor(None, self._arlo.request_snapshot)

    async def log_stderr(self, stream, label: str):
        """
        Continuously read from stderr and log the output.

        Args:
            stream: Stream to read from.
            label (str): Label for logging.
        """
        while True:
            try:
                line = await stream.stderr.readline()
                if line:
                    logger.debug("%s - %s: %s", self.name, label, line.decode().strip())
                else:
                    break
            except ValueError:
                pass

    async def shutdown_when_idle(self):
        """Shutdown the camera when it becomes idle."""
        if self.get_state() != "idle":
            logger.info("%s active, waiting...", self.name)
            while self.get_state() != "idle":
                await asyncio.sleep(1)
        self.shutdown()

    def shutdown(self):
        """Immediate shutdown of the camera."""
        logger.info("Shutting down %s", self.name)
        for stream in [self.stream, self.proxy_stream]:
            if stream:  # Check if stream exists
                try:
                    stream.terminate()
                except ProcessLookupError:
                    # Handle the specific case where the process is gone
                    logger.debug("Process for %s already terminated.", self.name)
                except AttributeError:
                    # Handle the case when stream is None
                    logger.debug("Stream for %s is not initialized.", self.name)

    @property
    def state_event(self):
        """
        Get the state event object.

        Returns:
            asyncio.Event: The state event object.
        """
        return self._state_event

    @property
    def motion_event(self):
        """
        Get the motion event object.

        Returns:
            asyncio.Event: The motion event object.
        """
        return self._motion_event
