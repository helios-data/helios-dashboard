import math
import time
import random
from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# InfluxDB connection settings
INFLUX_URL = "http://localhost:8086"
TOKEN = "my-super-token"
ORG = "rocket"
BUCKET = "mock_data"

# Create client
client = InfluxDBClient(url=INFLUX_URL, token=TOKEN, org=ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

print("Starting sine-wave data stream")

t = 0
while True:
    # Generate noisy sine wave value
    value = math.sin(t) + random.uniform(-0.05, 0.05)

    # Create a data point
    point = (
        Point("sine_wave")
        .tag("source", "mock_generator")
        .field("value", value)
        .time(datetime.utcnow(), WritePrecision.NS)
    )

    # Write to InfluxDB
    write_api.write(bucket=BUCKET, org=ORG, record=point)

    print(f"[{datetime.now()}] → value={value:.3f}")

    t += 0.1
    time.sleep(1)