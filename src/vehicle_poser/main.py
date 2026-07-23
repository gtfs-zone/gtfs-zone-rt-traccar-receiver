import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

import redis.asyncio as aioredis
import uvicorn
from fastapi import FastAPI, Request
from railroad_club.trip_resolver import resolve_driver_trip
from sqlmodel import Session, create_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REDIS_URL = os.environ["REDIS_URL"]
DATABASE_URL = os.environ["DATABASE_URL"]
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8080"))

KNOTS_TO_MS = 0.514444
POSITION_TTL = 60

_engine = create_engine(DATABASE_URL)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.redis = aioredis.from_url(REDIS_URL)
    yield
    await app.state.redis.aclose()


app = FastAPI(title="vehicle-poser", lifespan=lifespan)


def _resolve_trip(username: str) -> str | None:
    with Session(_engine) as session:
        return resolve_driver_trip(username, session)


def _to_epoch(fix_time: object) -> int | None:
    """Traccar sends fixTime as an ISO-8601 string; cafe-car needs epoch seconds."""
    if fix_time is None:
        return None
    if isinstance(fix_time, int | float):
        return int(fix_time)
    try:
        text = str(fix_time).replace("Z", "+00:00")
        return int(datetime.fromisoformat(text).timestamp())
    except (ValueError, TypeError):
        log.warning("Could not parse fixTime %r", fix_time)
        return None


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/forward")
async def forward(request: Request) -> dict[str, str]:
    body = await request.json()
    device = body.get("device") or {}
    position = body.get("position") or {}

    username = device.get("uniqueId")
    if not username:
        log.warning("Forward payload missing device.uniqueId")
        return {"status": "ignored"}

    trip_id = await asyncio.to_thread(_resolve_trip, username)
    if trip_id is None:
        log.warning("No active rule for driver=%s", username)

    speed = position.get("speed")
    record = {
        "driver": username,
        "trip_id": trip_id,
        "lat": position.get("latitude"),
        "lon": position.get("longitude"),
        "bearing": position.get("course"),
        "speed": round(speed * KNOTS_TO_MS, 4) if speed is not None else None,
        "timestamp": _to_epoch(position.get("fixTime")),
    }

    device_slug = position.get("deviceId") or "traccar"
    key = f"vehicle:{username}:{device_slug}"
    await app.state.redis.setex(key, POSITION_TTL, json.dumps(record))
    log.info(
        "Stored %s lat=%s lon=%s trip_id=%s",
        key,
        record["lat"],
        record["lon"],
        trip_id,
    )
    return {"status": "ok"}


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=HTTP_PORT)


if __name__ == "__main__":
    main()
