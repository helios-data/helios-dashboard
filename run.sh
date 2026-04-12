docker build --no-cache -t influx-grafana-python .
docker run -p 3000:3000 -p 8086:8086 influx-grafana-python