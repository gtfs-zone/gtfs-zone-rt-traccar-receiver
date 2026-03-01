# OwnTrack Redis Bridge

Tiny async Python service that bridges OwnTracks MQTT location events to Redis.

## What it does

Subscribes to `owntracks/+/+`, filters for `_type=location` payloads, and writes one key per user to Redis DB 2, overwriting on each update.

## Environment Variables

| Variable | Example | Description |
|---|---|---|
| `MQTT_BROKER` | `tcp://nanomq:1883` | MQTT broker URL (tcp scheme, host, port) |
| `REDIS_URL` | `redis://redis:6379/2` | Redis connection URL including DB number |

Both are required — the service will exit with `KeyError` if either is missing.

## Redis Key Scheme

- **Key:** `owntracks:{user}` (one per OwnTracks username)
- **Value:** Raw JSON bytes of the location payload as published by the device
- **DB:** 2 (set via `REDIS_URL`)
- **TTL:** None — latest location persists until overwritten

## Build

```sh
docker build -t owntrack-redis-bridge .
```

## Run Locally

```sh
docker run --rm \
  -e MQTT_BROKER=tcp://nanomq:1883 \
  -e REDIS_URL=redis://redis:6379/2 \
  owntrack-redis-bridge
```

## Test

```sh
# Publish a location event
mosquitto_pub -t owntracks/alice/phone -m '{"_type":"location","lat":51.5,"lon":-0.1,"tst":1}'

# Verify Redis (DB 2)
redis-cli -n 2 GET owntracks:alice
```
