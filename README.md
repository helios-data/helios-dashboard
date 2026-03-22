# Dashboard

Run with `docker compose up --build`

- Grafana: Port `3000`
  - Login: `admin`/`admin`
- InfluxDB: Port `8086`
  - Login: `admin`/`admin123`

## Mock Data

Requires `influxdb_client`, run `streaming.py` to stream data to the influx container.

## Planning

Package entire repo as docker container. Refer to the [helios livestream repo](https://github.com/helios-data/helios-livestreaming/blob/jason/docker-testing/Dockerfile)