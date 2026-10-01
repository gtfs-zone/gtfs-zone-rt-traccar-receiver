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
from gtfs_zone_db_models.trip_resolver import ResolvedTrip, resolve_tracker_trip
from gtfs_zone_db_models.vehicle_keys import vehicle_key
from sqlmodel import Session, create_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REDIS_URL = os.environ["REDIS_URL"]
DATABASE_URL = os.environ["DATABASE_URL"]
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8080"))
# Redis key namespace for written positions. Defaults to the live "vehicle"
# namespace that rt-api reads. Set this to a shadow prefix (e.g.
# "shadow:vehicle") to run a second pipeline alongside the live feed without
# clobbering the keys rt-api serves from. The part after the prefix comes
# from gtfs-zone-db-models, so it cannot drift from what rt-api reads back.
KEY_PREFIX = os.environ.get("VEHICLE_KEY_PREFIX", "vehicle")

KNOTS_TO_MS = 0.514444
POSITION_TTL = 60

_engine = create_engine(DATABASE_URL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.redis = aioredis.from_url(REDIS_URL)
    yield
    await app.state.redis.aclose()


app = FastAPI(title="rt-traccar-receiver", lifespan=lifespan)


def _resolve_trip(device_key: str) -> ResolvedTrip | None:
    with Session(_engine) as session:
        return resolve_tracker_trip(device_key, session)


def _to_epoch(fix_time: object) -> int | None:
    """Traccar sends fixTime as an ISO-8601 string; rt-api needs epoch seconds."""
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

    # Traccar speaks the secret device key; nothing downstream does. This is
    # the one edge that translates, and the resolver hands back the tracker's
    # surrogate id along with the trip.
    device_key = device.get("uniqueId")
    if not device_key:
        log.warning("Forward payload missing device.uniqueId")
        return {"status": "ignored"}

    resolved = await asyncio.to_thread(_resolve_trip, device_key)
    if resolved is None:
        # No such tracker, so no surrogate to key the record by and nothing to
        # write. A tracker that exists but has no active rule is a different
        # answer: it still gets a record, with no trip, and draws unmatched.
        log.warning("No tracker for the posted device key")
        return {"status": "ignored"}
    if resolved.trip_id is None:
        log.warning("No active rule for tracker=%s", resolved.tracker_id)

    speed = position.get("speed")
    # Traccar's own device id names the vehicle in the published feed; without
    # it the feed falls back to the tracker's nickname.
    device_id = position.get("deviceId")
    vehicle_id = str(device_id) if device_id is not None else None
    record = {
        "tracker_id": resolved.tracker_id,
        "vehicle_id": vehicle_id,
        "trip_id": resolved.trip_id,
        # The service date the rule's window started on, which is what
        # rt-delay-estimator keys predictions by and rt-api dedups vehicles by.
        # None alongside a None trip_id: there is no run to date.
        "start_date": (
            resolved.service_date.strftime("%Y%m%d")
            if resolved.service_date is not None
            else None
        ),
        "lat": position.get("latitude"),
        "lon": position.get("longitude"),
        "bearing": position.get("course"),
        "speed": round(speed * KNOTS_TO_MS, 4) if speed is not None else None,
        "timestamp": _to_epoch(position.get("fixTime")),
    }

    key = f"{KEY_PREFIX}:{vehicle_key(resolved.tracker_id, vehicle_id)}"
    await app.state.redis.setex(key, POSITION_TTL, json.dumps(record))
    log.info(
        "Stored %s lat=%s lon=%s trip_id=%s start_date=%s",
        key,
        record["lat"],
        record["lon"],
        resolved.trip_id,
        record["start_date"],
    )
    return {"status": "ok"}


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=HTTP_PORT)


if __name__ == "__main__":
    main()
