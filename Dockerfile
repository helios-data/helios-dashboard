# ---- Stage 1: get influxdb binaries ----
FROM influxdb:2.7 AS influx

# ---- Stage 2: get grafana binaries ----
FROM grafana/grafana-oss:11.1.4 AS grafana

# ---- Stage 3: build Python SDK and dependencies ----
FROM python:3.13-slim AS python-builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    protobuf-compiler \
    libprotobuf-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock* ./

# Copy SDK and build it
COPY helios-python-sdk/ ./helios-python-sdk/
COPY falcon-protos/ ./falcon-protos/

# Copy source
COPY src/ ./src/

RUN mkdir -p src/generated && \
    uv run protoc \
    -I=falcon-protos \
    --python_betterproto2_out=src/generated \
    $(find falcon-protos -name "*.proto")

RUN uv sync --frozen --no-dev

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

# Copy Python dependencies from builder
COPY --from=python-builder /build/.venv /app/.venv

# Set PATH to include local Python packages
ENV PATH="/app/.venv/bin:$PATH"

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

# Python script and SDK
COPY src/main.py /app/main.py
COPY helios-python-sdk/ /app/helios-python-sdk/

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN mkdir -p \
    /var/lib/grafana \
    /var/lib/grafana/dashboards \
    /var/log/grafana

EXPOSE 3000 8086

ENTRYPOINT ["/entrypoint.sh"]