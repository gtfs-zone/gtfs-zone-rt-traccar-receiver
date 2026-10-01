# CLAUDE.md

## Overview

Tiny async Python service that receives [Traccar](https://www.traccar.org/) position forwards over HTTP and writes normalized vehicle positions to Redis. The entire service logic lives in `src/gtfs_zone_rt_traccar_receiver/main.py`.

## Architecture

**Flow:** Traccar Client app (phone) → Traccar server → HTTP `POST /forward` → this service → Redis → rt-api

1. `main()` runs a FastAPI/uvicorn HTTP server; Redis is opened in the `lifespan` and stored on `app.state.redis`.
2. `POST /forward` receives Traccar's `json` forward (`{"device": Device, "position": Position}`), transforms the payload, resolves the trip, and writes to Redis with a 60-second TTL via `setex`. `GET /health` is a liveness probe.

**Payload transformation:** Traccar fields are mapped to a normalized record:
- `device.uniqueId` is the tracker's **secret** `device_key`. It is translated here and nowhere else: the record's `tracker_id` is the tracker's non-secret surrogate `id`.
- `trip_id` resolved server-side via `resolve_tracker_trip(device_key)` (schedule-based), or `null`
- `start_date` is the resolved run's service date (`YYYYMMDD`), or `null` alongside a `null` `trip_id`
- `position.latitude`, `position.longitude` → `lat`, `lon`
- `position.course` → `bearing`
- `position.speed` (knots) → `speed` (m/s, ×0.514444, 4 decimal places)
- `position.fixTime` (ISO-8601) → `timestamp` (epoch seconds)

**Redis key scheme:**
- Key: `{VEHICLE_KEY_PREFIX}:{tracker_id}:{position.deviceId}` (default prefix
  `vehicle`), built by `gtfs_zone_db_models.vehicle_keys.vehicle_key`. A position
  with no `deviceId` keys on the bare `tracker_id`.
- Value: JSON of the normalized record
- TTL: 60 seconds

The key identifies a *vehicle*, not a trip: a device that changes trip overwrites its own record. rt-api labels the vehicle in the public GTFS-RT feed by the record's `vehicle_id` (the Traccar `deviceId`), falling back to the tracker's `nickname` from the DB. `tracker_id` is the surrogate, not a credential; the credential is `device_key` and never leaves this service.

An unknown `device.uniqueId` is dropped. A known tracker with no active rule is written with a `null` `trip_id` so it still draws as an unassigned vehicle.

## Environment Variables

| Variable | Example | Description |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379/1` | Redis connection URL including DB number |
| `DATABASE_URL` | `postgresql+psycopg2://.../postgres` | Postgres URL for tracker-rule trip resolution |
| `HTTP_PORT` | `8080` | Port the HTTP server listens on (default `8080`) |
| `VEHICLE_KEY_PREFIX` | `vehicle` | Redis key namespace for written positions (default `vehicle`) |

`REDIS_URL` and `DATABASE_URL` are required. The service exits with `KeyError` if either is missing.

## Development

Dependencies are managed with `uv` (Python 3.13).

```sh
# Install dependencies
uv sync

# Install git hooks (required once per clone)
uv run pre-commit install

# Run the service locally (requires Redis and Postgres)
REDIS_URL=redis://localhost:6379/1 \
DATABASE_URL=postgresql+psycopg2://postgres:mysecretpassword@localhost:5432/postgres \
  uv run python -m gtfs_zone_rt_traccar_receiver.main

# Build and push are CI's job: pushing to main publishes :latest and :<short-sha>.
# `make cp` copies that short sha for the gtfs-zone-infra manifest bump.
make cp
```

## Testing

```sh
# Simulate a Traccar json forward (speed in knots, course in degrees)
curl -X POST http://localhost:8080/forward \
  -H 'Content-Type: application/json' \
  -d '{"device":{"uniqueId":"alice"},
       "position":{"latitude":51.5,"longitude":-0.1,"course":90,"speed":10,
                   "fixTime":"2026-07-23T12:00:00Z","deviceId":7}}'

# Verify the Redis key (use the DB set in REDIS_URL)
redis-cli -n 1 GET vehicle:alice:7
```

## Rules

- Module loggers are named `log`, never `logger`: `log = logging.getLogger(__name__)`
