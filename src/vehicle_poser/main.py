import asyncio
import json
import logging
import os
from urllib.parse import urlparse

import aiomqtt
import redis.asyncio as aioredis
from sqlmodel import Session, create_engine

from railroad_club.trip_resolver import resolve_driver_trip

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MQTT_BROKER = os.environ["MQTT_BROKER"]
MQTT_USERNAME = os.environ.get("MQTT_USERNAME")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")
REDIS_URL = os.environ["REDIS_URL"]
DATABASE_URL = os.environ["DATABASE_URL"]

RECONNECT_DELAY_INITIAL = 1
RECONNECT_DELAY_MAX = 60

_engine = create_engine(DATABASE_URL)


def _resolve_trip(username: str) -> str | None:
    with Session(_engine) as session:
        return resolve_driver_trip(username, session)


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
        device = parts[2]

        if device == "auto":
            trip_id = await asyncio.to_thread(_resolve_trip, user)
            if trip_id is None:
                log.warning("No active rule for driver=%s (device=auto)", user)
        else:
            trip_id = device

        record = {
            "driver": user,
            "trip_id": trip_id,
            "lat": payload.get("lat"),
            "lon": payload.get("lon"),
            "bearing": payload.get("cog"),
            "speed": round(payload["vel"] / 3.6, 4) if payload.get("vel") is not None else None,
            "timestamp": payload.get("tst"),
        }
        key = f"vehicle:{user}:{device}"
        await redis.setex(key, 60, json.dumps(record))
        log.info("Stored %s lat=%s lon=%s trip_id=%s", key, record["lat"], record["lon"], trip_id)


async def main() -> None:
    parsed = urlparse(MQTT_BROKER)
    host = parsed.hostname
    port = parsed.port or 1883

    redis = aioredis.from_url(REDIS_URL)
    delay = RECONNECT_DELAY_INITIAL

    while True:
        try:
            async with aiomqtt.Client(hostname=host, port=port, username=MQTT_USERNAME, password=MQTT_PASSWORD) as client:
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
