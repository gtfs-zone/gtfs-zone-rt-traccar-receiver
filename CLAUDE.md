# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Tiny async Python service that receives [Traccar](https://www.traccar.org/) position forwards over HTTP and writes normalized vehicle positions to Redis. The entire service logic lives in `src/vehicle_poser/main.py`.

## Architecture

**Flow:** Traccar Client app (phone) → Traccar server → HTTP `POST /forward` → this service → Redis → cafe-car

1. `main()` runs a FastAPI/uvicorn HTTP server; Redis is opened in the `lifespan` and stored on `app.state.redis`.
2. `POST /forward` receives Traccar's `json` forward (`{"device": Device, "position": Position}`), transforms the payload, resolves the trip, and writes to Redis with a 60-second TTL via `setex`. `GET /health` is a liveness probe.

**Payload transformation** — Traccar fields are mapped to a normalized record:
- `device.uniqueId` → `tracker_id` (the tracker's **secret** id; never exposed in a public feed)
- `trip_id` resolved server-side via `resolve_tracker_trip(tracker_id)` (schedule-based), or `null`
- `position.latitude`, `position.longitude` → `lat`, `lon`
- `position.course` → `bearing`
- `position.speed` (knots) → `speed` (m/s, ×0.514444, 4 decimal places)
- `position.fixTime` (ISO-8601) → `timestamp` (epoch seconds)

**Redis key scheme:**
- Key: `{VEHICLE_KEY_PREFIX}:{tracker_id}:{position.deviceId or "traccar"}` (default prefix `vehicle`)
- Value: JSON of the normalized record
- TTL: 60 seconds

cafe-car scans `vehicle:{tracker_id}:*` and labels the vehicle in the public GTFS-RT feed by the tracker's `nickname` (from the DB) — the `tracker_id` is a secret credential and stays internal to Redis.

## Environment Variables

| Variable | Example | Description |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379/1` | Redis connection URL including DB number |
| `DATABASE_URL` | `postgresql+psycopg2://.../postgres` | Postgres URL for tracker-rule trip resolution |
| `HTTP_PORT` | `8080` | Port the HTTP server listens on (default `8080`) |
| `VEHICLE_KEY_PREFIX` | `vehicle` | Redis key namespace for written positions (default `vehicle`) |

`REDIS_URL` and `DATABASE_URL` are required — the service exits with `KeyError` if either is missing.

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
  uv run python -m vehicle_poser.main

# Build and push Docker image (requires clean, pushed git state)
make push
```

## Rules

- Never add Co-Authored-By trailers to commit messages.

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
