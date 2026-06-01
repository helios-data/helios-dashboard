#!/bin/bash
set -e

# Clear any old locks
rm -f /var/lib/grafana/grafana.db.lock

echo "Starting InfluxDB..."
influxd &
INFLUXDB_PID=$!

# Wait for InfluxDB API to be alive
echo "Waiting for InfluxDB API..."
MAX_WAIT=30
WAIT_COUNT=0
until curl -s http://localhost:8086/health > /dev/null 2>&1 || [ $WAIT_COUNT -ge $MAX_WAIT ]; do
  WAIT_COUNT=$((WAIT_COUNT + 1))
  sleep 1
done

if [ $WAIT_COUNT -ge $MAX_WAIT ]; then
  echo "ERROR: InfluxDB failed to start"
  exit 1
fi

echo "InfluxDB API is ready"

SETUP_MARKER=/root/.influxdbv2/.setup_complete

if [ ! -f "$SETUP_MARKER" ]; then
  echo "First run: Setting up InfluxDB..."
  influx setup \
    --username "$DOCKER_INFLUXDB_INIT_USERNAME" \
    --password "$DOCKER_INFLUXDB_INIT_PASSWORD" \
    --org "$DOCKER_INFLUXDB_INIT_ORG" \
    --bucket "$DOCKER_INFLUXDB_INIT_BUCKET" \
    --token "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN" \
    --force
  touch "$SETUP_MARKER"
  echo "InfluxDB setup complete"
else
  echo "InfluxDB already initialized"
fi

# Ensure Grafana datasource uses the same InfluxDB token and org/bucket configuration
cat > /etc/grafana/provisioning/datasources/influxdb.yaml <<EOF
apiVersion: 1

datasources:
  - uid: influxdb-uid
    name: InfluxDB
    type: influxdb
    access: proxy
    url: http://localhost:8086
    jsonData:
      version: Flux
      organization: "$DOCKER_INFLUXDB_INIT_ORG"
      defaultBucket: "$DOCKER_INFLUXDB_INIT_BUCKET"
    secureJsonData:
      token: "$DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"
    isDefault: true
EOF

echo "Starting Grafana..."
grafana server \
  --homepath=/usr/share/grafana \
  --config=/etc/grafana/grafana.ini \
  cfg:default.paths.provisioning=/etc/grafana/provisioning \
  cfg:default.paths.data=/var/lib/grafana \
  cfg:default.paths.logs=/var/log/grafana \
  cfg:default.paths.plugins=/var/lib/grafana/plugins &

# Wait for InfluxDB to be fully ready for writes
# This is critical: token-based auth may not be immediately available
echo "Waiting for InfluxDB to be fully ready for authenticated writes..."
sleep 10

echo "Starting Python script..."
/app/.venv/bin/python /app/src/main.py

wait