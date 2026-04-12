# ---- Stage 1: get influxdb binaries ----
FROM influxdb:2.7 AS influx

# ---- Stage 2: get grafana binaries ----
FROM grafana/grafana-oss:11.1.4 AS grafana

# ---- Final image ----
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy influxdb
COPY --from=influx /usr/local/bin/influx /usr/local/bin/influx
COPY --from=influx /usr/local/bin/influxd /usr/local/bin/influxd

# Copy grafana
COPY --from=grafana /usr/share/grafana /usr/share/grafana
COPY --from=grafana /etc/grafana /etc/grafana
COPY --from=grafana /usr/share/grafana/bin/grafana-server /usr/local/bin/grafana-server
COPY --from=grafana /usr/share/grafana/bin/grafana /usr/local/bin/grafana

# Environment variables (same as docker-compose)
ENV DOCKER_INFLUXDB_INIT_MODE=setup
ENV DOCKER_INFLUXDB_INIT_USERNAME=admin
ENV DOCKER_INFLUXDB_INIT_PASSWORD=admin123
ENV DOCKER_INFLUXDB_INIT_ORG=rocket
ENV DOCKER_INFLUXDB_INIT_BUCKET=mock_data
ENV DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=my-super-token

ENV GF_SECURITY_ADMIN_USER=admin
ENV GF_SECURITY_ADMIN_PASSWORD=admin
ENV GF_DASHBOARDS_MIN_REFRESH_INTERVAL=1s

# Grafana provisioning
COPY grafana/provisioning /etc/grafana/provisioning
COPY grafana/dashboards /var/lib/grafana/dashboards

# Python script
COPY src/main.py /app/main.py

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN mkdir -p \
    /var/lib/grafana \
    /var/lib/grafana/dashboards \
    /var/log/grafana

EXPOSE 3000 8086

ENTRYPOINT ["/entrypoint.sh"]