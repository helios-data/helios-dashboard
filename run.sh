docker build -t dashboard .

docker run \
    -p 3000:3000 \
    -p 8086:8086 \
    -v ~/Desktop/Projects/rocket/helios-launcher/src/tmp/influx2:/root/.influxdbv2 \
    -e VERBOSE=1 \
    -e STANDALONE=1 \
    dashboard