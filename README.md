# vehicle-poser

Tiny async Python service that ingests [OwnTracks](https://owntracks.org/) location events via MQTT and writes normalized vehicle positions to Redis.

Part of a larger stack; see [deploy-gtfs-rt](https://git.kcfam.us/gtfs.zone/deploy-gtfs-rt) for the full deployment.

### How it fits together

```
OwnTracks app (phone)
    └─> MQTT broker (see cafe-car)
            └─> bridge service
                    └─> Redis (vehicle:{username} keys, 60s TTL)
                            └─> cafe-car (serves GTFS-RT feeds)
```

The bridge subscribes to `owntracks/+/+`, filters for `_type=location` events, transforms the payload to a normalized record, and writes it to Redis with a 60-second TTL. If the MQTT connection drops, it reconnects with exponential backoff (1s → 60s max).

---

## Payload transformation

OwnTracks fields are mapped as follows:

| OwnTracks field | Redis record field | Notes |
|---|---|---|
| topic `owntracks/{user}/{device}` | `driver`, `trip_id` | split from topic |
| `lat`, `lon`, `tst` | `lat`, `lon`, `timestamp` | passed through |
| `cog` | `bearing` | degrees |
| `vel` | `speed` | converted km/h → m/s, 4 decimal places |

**Redis key:** `vehicle:{username}` — one key per OwnTracks username, overwritten on each update.

---

## Environment variables

| Variable | Example | Description |
|---|---|---|
| `MQTT_BROKER` | `tcp://localhost:1883` | MQTT broker URL (tcp scheme) |
| `REDIS_URL` | `redis://redis:6379/1` | Redis connection URL including DB number |

Both are required — the service exits with `KeyError` if either is missing.

---

## Running

```sh
# Install dependencies (Python 3.13, uv)
uv sync

# Install git hooks (required once per clone)
uv run pre-commit install

# Run locally (requires MQTT broker and Redis)
MQTT_BROKER=tcp://localhost:1883 REDIS_URL=redis://localhost:6379/1 \
  uv run python -m vehicle_poser.main

# Build and push Docker image (requires clean, pushed git state)
make push
```

---

## Testing

```sh
# Publish a location event (vel in km/h, cog in degrees)
mosquitto_pub -t owntracks/alice/phone \
  -m '{"_type":"location","lat":51.5,"lon":-0.1,"tst":1,"vel":36,"cog":90}'

# Verify the Redis key (use the DB set in REDIS_URL)
redis-cli -n 1 GET vehicle:alice
```

Expected Redis value:

```json
{"driver": "alice", "trip_id": "phone", "lat": 51.5, "lon": -0.1, "bearing": 90, "speed": 10.0, "timestamp": 1}
```
