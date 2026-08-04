# vehicle-poser

Tiny async Python service that receives [Traccar](https://www.traccar.org/) position forwards over HTTP and writes normalized vehicle positions to Redis.

Part of a larger stack; see [deploy-gtfs-rt](https://git.kcfam.us/gtfs.zone/deploy-gtfs-rt) for the full deployment.

### How it fits together

```
Traccar Client app (phone)
    └─> Traccar server (:5055 osmand ingest)
            └─> forward.type=json  POST /forward
                    └─> vehicle-poser (this service)
                            └─> Redis (vehicle:{tracker_id}:{deviceId} keys, 60s TTL)
                                    └─> cafe-car (serves GTFS-RT feeds)
```

Traccar is configured with `forward.type=json` / `forward.url=http://vehicle-poser:8080/forward`.
On each POST the service reads `device.uniqueId` (which is the tracker's secret
id), resolves the tracker's active `trip_id` via railroad-club's schedule-based
`resolve_tracker_trip`, transforms the payload to a normalized record, and writes
it to Redis with a 60-second TTL. cafe-car labels the vehicle in the public feed
by the tracker's `nickname` (resolved from the DB), never by this secret id.

---

## Payload transformation

Traccar `json` forward sends `{"position": Position, "device": Device}`. Fields
are mapped as follows:

| Traccar field | Redis record field | Notes |
|---|---|---|
| `device.uniqueId` | `tracker_id` | = the tracker's secret id |
| - | `trip_id` | resolved server-side via `resolve_tracker_trip(tracker_id)` (schedule-based), or `null` |
| `position.latitude`, `position.longitude` | `lat`, `lon` | passed through |
| `position.course` | `bearing` | degrees |
| `position.speed` | `speed` | converted **knots → m/s** (×0.514444), 4 decimal places |
| `position.fixTime` | `timestamp` | ISO-8601 parsed to epoch seconds |

**Redis key:** `{VEHICLE_KEY_PREFIX}:{uniqueId}:{position.deviceId or "traccar"}` (default prefix `vehicle`), overwritten on each update.

---

## Environment variables

| Variable | Example | Description |
|---|---|---|
| `REDIS_URL` | `redis://redis:6379/1` | Redis connection URL including DB number |
| `DATABASE_URL` | `postgresql+psycopg2://.../postgres` | Postgres URL for tracker-rule trip resolution |
| `HTTP_PORT` | `8080` | Port the HTTP server listens on (default `8080`) |
| `VEHICLE_KEY_PREFIX` | `vehicle` | Redis key namespace for written positions (default `vehicle`). Set to a shadow prefix (e.g. `shadow:vehicle`) for dual-run comparison so the Traccar pipeline doesn't clobber the live feed. |

`REDIS_URL` and `DATABASE_URL` are required. The service exits with `KeyError` if either is missing.

---

## Running

```sh
# Install dependencies (Python 3.13, uv)
uv sync

# Install git hooks (required once per clone)
uv run pre-commit install

# Run locally (requires Redis and Postgres)
REDIS_URL=redis://localhost:6379/1 \
DATABASE_URL=postgresql+psycopg2://postgres:mysecretpassword@localhost:5432/postgres \
  uv run python -m vehicle_poser.main

# Build and push Docker image (requires clean, pushed git state)
make push
```

---

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

Expected Redis value (`trip_id` is `null` unless tracker `alice` has an active rule):

```json
{"tracker_id": "alice", "trip_id": null, "lat": 51.5, "lon": -0.1, "bearing": 90, "speed": 5.1444, "timestamp": 1784808000}
```
