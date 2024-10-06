"""MQTT functions for Arlo's Camera devices."""

import base64 as b64
import json
import logging
import asyncio
import time
import aiomqtt  # pylint: disable=import-error
from aiostream import stream  # pylint: disable=import-error
from decouple import config  # pylint: disable=import-error

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

# For PyRight issue which doesn't work with decouple
env_params = {
    "MQTT_BROKER": MQTT_BROKER,
    "MQTT_PORT": MQTT_PORT,
    "MQTT_USER": MQTT_USER,
    "MQTT_PASS": MQTT_PASS,
    "MQTT_RECONNECT_INTERVAL": MQTT_RECONNECT_INTERVAL,
    "MQTT_TOPIC_PICTURE": MQTT_TOPIC_PICTURE,
    "MQTT_TOPIC_CONTROL": MQTT_TOPIC_CONTROL,
    "MQTT_TOPIC_STATUS": MQTT_TOPIC_STATUS,
    "MQTT_TOPIC_MOTION": MQTT_TOPIC_MOTION,
}


async def mqtt_client(cameras, bases):
    """
    Async mqtt client, initiaties various generators and readers
    """
    while True:
        try:
            async with aiomqtt.Client(
                hostname=env_params["MQTT_BROKER"],
                port=env_params["MQTT_PORT"],
                username=env_params["MQTT_USER"],
                password=env_params["MQTT_PASS"],
            ) as client:
                logger.info("MQTT client connected to %s", env_params["MQTT_BROKER"])
                await asyncio.gather(
                    # Generators/Readers
                    mqtt_reader(client, cameras + bases),
                    device_status(client, cameras + bases),
                    motion_stream(client, cameras),
                    pic_streamer(client, cameras),
                )
        except aiomqtt.MqttError as error:
            logger.info('MQTT "%s". reconnecting.', error)
            await asyncio.sleep(env_params["MQTT_RECONNECT_INTERVAL"])


async def pic_streamer(client, cameras):
    """
    Merge picture streams from all cameras and publish to MQTT
    """
    pics = stream.merge(*[c.get_pictures() for c in cameras])
    async with pics.stream() as streamer:
        async for name, data in streamer:
            timestamp = str(time.time()).replace(".", "")
            await client.publish(
                MQTT_TOPIC_PICTURE.format(name=name),
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
                MQTT_TOPIC_STATUS.format(name=name), payload=json.dumps(status)
            )


async def motion_stream(client, cameras):
    """
    Merge motion events from all cameras and publish to MQTT
    """
    motion_states = stream.merge(*[c.listen_motion() for c in cameras])
    async with motion_states.stream() as streamer:
        async for name, motion in streamer:
            await client.publish(
                MQTT_TOPIC_MOTION.format(name=name), payload=json.dumps(motion)
            )


async def mqtt_reader(client, devices):
    """
    Subscribe to control topics, and pass messages to individual cameras
    """
    devs = {MQTT_TOPIC_CONTROL.format(name=d.name): d for d in devices}
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
