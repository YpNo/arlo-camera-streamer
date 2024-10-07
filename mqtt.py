"""MQTT functions for Arlo's Camera devices."""

import base64 as b64
import json
import logging
import asyncio
import time
import aiomqtt  # pylint: disable=import-error # pyright: ignore [reportMissingImports]
from aiostream import (  # pylint: disable=import-error # pyright: ignore [reportMissingImports]
    stream,
)
from decouple import (  # pylint: disable=import-error # pyright: ignore [reportMissingImports]
    config,
)

MQTT_BROKER = config("MQTT_BROKER", cast=str, default="localhost")
MQTT_PORT = config("MQTT_PORT", cast=int, default=1883)
MQTT_USER = config("MQTT_USER", cast=str, default="arlo")
MQTT_PASS = config("MQTT_PASS", cast=str, default="arlo")
MQTT_RECONNECT_INTERVAL = config("MQTT_RECONNECT_INTERVAL", default=5)
MQTT_TOPIC_PICTURE = config("MQTT_TOPIC_PICTURE", default="arlo/picture/{name}")
# MQTT_TOPIC_LOCATION = config('MQTT_TOPIC_LOCATION', default='arlo/location')
MQTT_TOPIC_CONTROL = config("MQTT_TOPIC_CONTROL", default="arlo/control/{name}")
MQTT_TOPIC_STATUS = config("MQTT_TOPIC_STATUS", default="arlo/status/{name}")
MQTT_TOPIC_MOTION = config("MQTT_TOPIC_MOTION", default="arlo/motion/{name}")

DEBUG = config("DEBUG", default=False, cast=bool)

# Initialize logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def mqtt_client(cameras, bases):
    """
    Async mqtt client, initiaties various generators and readers
    """
    while True:
        try:
            async with aiomqtt.Client(
                hostname=MQTT_BROKER,  # pyright: ignore [reportArgumentType]
                port=MQTT_PORT,  # pyright: ignore [reportArgumentType]
                username=MQTT_USER,  # pyright: ignore [reportArgumentType]
                password=MQTT_PASS,  # pyright: ignore [reportArgumentType]
            ) as client:
                logger.info("MQTT client connected to %s", MQTT_BROKER)
                await asyncio.gather(
                    # Generators/Readers
                    mqtt_reader(client, cameras + bases),
                    device_status(client, cameras + bases),
                    motion_stream(client, cameras),
                    pic_streamer(client, cameras),
                )
        except aiomqtt.MqttError as error:
            logger.info('MQTT "%s". reconnecting.', error)
            await asyncio.sleep(MQTT_RECONNECT_INTERVAL)


async def pic_streamer(client, cameras):
    """
    Merge picture streams from all cameras and publish to MQTT
    """
    pics = stream.merge(*[c.get_pictures() for c in cameras])
    async with pics.stream() as streamer:
        async for name, data in streamer:
            timestamp = str(time.time()).replace(".", "")
            await client.publish(
                MQTT_TOPIC_PICTURE.format(  # pyright: ignore [reportAttributeAccessIssue]
                    name=name
                ),
                payload=json.dumps(
                    {
                        "filename": f"{timestamp} {name}.jpg",
                        "payload": b64.b64encode(data).decode("utf-8"),
                    }
                ),
            )


async def device_status(client, devices):
    """
    Merge device status from all devices and publish to MQTT
    """
    statuses = stream.merge(*[d.listen_status() for d in devices])
    async with statuses.stream() as streamer:
        async for name, status in streamer:
            await client.publish(
                MQTT_TOPIC_STATUS.format(  # pyright: ignore [reportAttributeAccessIssue]
                    name=name
                ),
                payload=json.dumps(status),
            )


async def motion_stream(client, cameras):
    """
    Merge motion events from all cameras and publish to MQTT
    """
    motion_states = stream.merge(*[c.listen_motion() for c in cameras])
    async with motion_states.stream() as streamer:
        async for name, motion in streamer:
            await client.publish(
                MQTT_TOPIC_MOTION.format(  # pyright: ignore [reportAttributeAccessIssue]
                    name=name
                ),
                payload=json.dumps(motion),
            )


async def mqtt_reader(client, devices):
    """
    Subscribe to control topics, and pass messages to individual cameras
    """
    devs = {
        MQTT_TOPIC_CONTROL.format(  # pyright: ignore [reportAttributeAccessIssue]
            name=d.name
        ): d
        for d in devices
    }
    async with client.messages() as messages:
        for name, _ in devs.items():
            await client.subscribe(name)
        async for message in messages:
            if message.topic.value in devs:
                asyncio.create_task(
                    devs[message.topic.value].mqtt_control(
                        message.payload.decode("utf-8")
                    )
                )
