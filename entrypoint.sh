#!/bin/bash
set -e

echo "Starting InfluxDB..."
influxd &

# wait for influx to start
until curl -s http://localhost:8086/health > /dev/null; do
  echo "Waiting for InfluxDB..."
  sleep 2
done

# Only run setup if DB not initialized
if [ ! -f /root/.influxdbv2/influxd.bolt ]; then
  echo "Setting up InfluxDB..."
  influx setup \
    --username $DOCKER_INFLUXDB_INIT_USERNAME \
    --password $DOCKER_INFLUXDB_INIT_PASSWORD \
    --org $DOCKER_INFLUXDB_INIT_ORG \
    --bucket $DOCKER_INFLUXDB_INIT_BUCKET \
    --token $DOCKER_INFLUXDB_INIT_ADMIN_TOKEN \
    --force
else
  echo "InfluxDB already initialized, skipping setup"
fi

echo "Starting Grafana..."
grafana server \
  --homepath=/usr/share/grafana \
  --config=/etc/grafana/grafana.ini \
  cfg:default.paths.provisioning=/etc/grafana/provisioning \
  cfg:default.paths.data=/var/lib/grafana \
  cfg:default.paths.logs=/var/log/grafana \
  cfg:default.paths.plugins=/var/lib/grafana/plugins &

echo "Starting Python script..."
python3 /app/src/main.py

wait