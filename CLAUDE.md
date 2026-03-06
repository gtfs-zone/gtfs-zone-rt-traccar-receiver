# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Tiny async Python service that bridges OwnTracks MQTT location events to Redis. The entire service logic lives in `src/owntrack_redis_bridge/main.py`.

## Architecture

**Flow:** OwnTracks device → MQTT broker (NanoMQ) → bridge service → Redis

1. `main()` connects to MQTT and Redis, then runs a reconnect loop with exponential backoff (1s → 60s max).
2. `process_messages()` subscribes to `owntracks/+/+`, filters for `_type=location`, transforms the payload, and writes to Redis with a 60-second TTL via `setex`.

**Payload transformation** — OwnTracks fields are mapped to a normalized record:
- Topic `owntracks/{user}/{device}` → `driver=user`, `trip_id=device`
- `lat`, `lon`, `tst` (timestamp) passed through directly
- `cog` → `bearing`
- `vel` (km/h) → `speed` (m/s, rounded to 4 decimal places)

**Redis key scheme:**
- Key: `vehicle:{user}` (one per OwnTracks username)
- Value: JSON of the normalized record (not raw OwnTracks payload)
- TTL: 60 seconds

## Environment Variables

| Variable | Example | Description |
|---|---|---|
| `MQTT_BROKER` | `tcp://nanomq:1883` | MQTT broker URL (tcp scheme, host, port) |
| `REDIS_URL` | `redis://redis:6379/1` | Redis connection URL including DB number |

Both are required — the service exits with `KeyError` if either is missing.

## NanoMQ Broker

The `docker-compose.yml` includes a NanoMQ MQTT broker alongside the bridge. NanoMQ is configured via `nanomq.conf` and `nanomq_acl.conf`:
- Anonymous connections are **disabled**; auth is delegated via HTTP POST to `http://host.docker.internal:8000/mqtt/auth`
- ACL: users may only publish to `owntracks/{their_username}/#`; all clients may subscribe to `owntracks/#`

## Development

Dependencies are managed with `uv` (Python 3.13).

```sh
# Install dependencies
uv sync

# Run the service locally (requires MQTT broker and Redis)
uv run python -m owntrack_redis_bridge.main

# Build Docker image
docker build -t owntrack-redis-bridge .

# Run full stack (NanoMQ + bridge)
docker compose up
```

## Testing

```sh
# Publish a location event (vel in km/h, cog in degrees)
mosquitto_pub -t owntracks/alice/phone \
  -m '{"_type":"location","lat":51.5,"lon":-0.1,"tst":1,"vel":36,"cog":90}'

# Verify Redis key (use the DB set in REDIS_URL)
redis-cli -n 1 GET vehicle:alice
```
