# AGENTS.md

Tiny FastAPI service that receives Traccar position forwards on `POST /forward`
and writes normalized vehicle positions to Redis for rt-api. Pushing to `main`
publishes the image; `make cp` copies the short sha for the gtfs-zone-infra bump.

## Architecture

All logic is in `src/gtfs_zone_rt_traccar_receiver/main.py`. The payload
mapping, Redis key scheme, env vars and a `curl` smoke test are in
[README.md](README.md).

- `device.uniqueId` is the tracker's **secret** `device_key`. It is translated
  to the non-secret surrogate `tracker_id` here and never leaves this service.
- Keys come from `gtfs_zone_db_models.vehicle_keys.vehicle_key`. A key
  identifies a vehicle, not a trip: a device that changes trip overwrites its
  own record.
- An unknown `device.uniqueId` is dropped. A known tracker with no active rule is
  still written, with a `null` `trip_id`, so it draws as unassigned.

## Conventions

- **Commits**: Conventional Commits, enforced by the `commit-msg` hook. Setup,
  release and `gtfs-zone-db-models` changes are in [CONTRIBUTING.md](CONTRIBUTING.md).
- **Logging**: module loggers are named `log`, never `logger`.
- **Plans**: write plans to `CURRENT_PLAN.md` at the repo root as a
  checklist (`- [ ]`), ticked off as work lands. It is neither tracked nor
  gitignored: never stage or commit it.
