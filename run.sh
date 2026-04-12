docker build --no-cache -t influx-grafana-python .

docker run \
    -p 3000:3000 \
    -p 8086:8086 \
    -v influxdb_data:/root/.influxdbv2 \
    -v grafana_data:/var/lib/grafana \
    influx-grafana-python