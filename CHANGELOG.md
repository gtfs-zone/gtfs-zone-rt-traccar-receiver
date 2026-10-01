## v0.2.1 (2026-10-01)

## v0.2.0 (2026-10-01)

### BREAKING CHANGE

- the module is now gtfs_zone_rt_traccar_receiver

### Feat

- key positions on the vehicle, via the shared helper
- speak the tracker surrogate everywhere but the Traccar edge
- identify devices by Tracker id, not Driver username
- add VEHICLE_KEY_PREFIX for dual-run shadow isolation
- replace MQTT subscriber with Traccar HTTP forward shim
- resolve "auto" device to trip_id via driver rules
- support MQTT username and password

### Fix

- install git in builder so uv can fetch railroad-club

### Refactor

- rename the package to gtfs-zone-rt-traccar-receiver

## v0.1.1 (2026-03-10)

### Fix

- use acl http instead of file

### Refactor

- rename api to cafe-car
- rm compose
- rename src to vehicle-poser

## v0.1.0 (2026-03-02)
