import asyncio
import json
import logging
import os
from urllib.parse import urlparse

import aiomqtt
import redis.asyncio as aioredis

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MQTT_BROKER = os.environ["MQTT_BROKER"]
REDIS_URL = os.environ["REDIS_URL"]

RECONNECT_DELAY_INITIAL = 1
RECONNECT_DELAY_MAX = 60


async def process_messages(client: aiomqtt.Client, redis: aioredis.Redis) -> None:
    await client.subscribe("owntracks/+/+")
    async for message in client.messages:
        try:
            payload = json.loads(message.payload)
        except (json.JSONDecodeError, ValueError):
            log.warning("Failed to decode JSON from topic %s", message.topic)
            continue

        if payload.get("_type") != "location":
            continue

        parts = str(message.topic).split("/")
        user = parts[1]
        key = f"owntracks:{user}"
        await redis.set(key, message.payload)
        log.info("Stored %s lat=%s lon=%s", key, payload.get("lat"), payload.get("lon"))


async def main() -> None:
    parsed = urlparse(MQTT_BROKER)
    host = parsed.hostname
    port = parsed.port or 1883

    redis = aioredis.from_url(REDIS_URL)
    delay = RECONNECT_DELAY_INITIAL

    while True:
        try:
            async with aiomqtt.Client(hostname=host, port=port) as client:
                log.info("Connected to MQTT broker %s:%s", host, port)
                delay = RECONNECT_DELAY_INITIAL
                await process_messages(client, redis)
        except aiomqtt.MqttError as exc:
            log.warning("MQTT error: %s — reconnecting in %ss", exc, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, RECONNECT_DELAY_MAX)
        except asyncio.CancelledError:
            log.info("Shutting down")
            break

    await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
