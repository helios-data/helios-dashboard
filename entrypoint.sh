#!/bin/bash
set -e

echo "Starting InfluxDB..."
influxd &

# wait for influx to start
sleep 5

echo "Setting up InfluxDB..."
influx setup \
  --username $DOCKER_INFLUXDB_INIT_USERNAME \
  --password $DOCKER_INFLUXDB_INIT_PASSWORD \
  --org $DOCKER_INFLUXDB_INIT_ORG \
  --bucket $DOCKER_INFLUXDB_INIT_BUCKET \
  --token $DOCKER_INFLUXDB_INIT_ADMIN_TOKEN \
  --force

echo "Starting Grafana..."
grafana server \
  --homepath=/usr/share/grafana \
  --config=/etc/grafana/grafana.ini \
  cfg:default.paths.provisioning=/etc/grafana/provisioning \
  cfg:default.paths.data=/var/lib/grafana \
  cfg:default.paths.logs=/var/log/grafana \
  cfg:default.paths.plugins=/var/lib/grafana/plugins &

echo "Starting Python script..."
python3 /app/main.py

wait