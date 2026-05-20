import asyncio
import logging
import os
import sys
from datetime import datetime

from helios import HeliosClient
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from generated import TelemetryPacket, FlightState

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# InfluxDB configuration
INFLUX_URL = os.getenv("INFLUX_URL", "http://127.0.0.1:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "my-super-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "rocket")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "mock_data")


def validate_influx_config() -> None:
    if not INFLUX_TOKEN:
        logger.error("Missing InfluxDB token. Set INFLUX_TOKEN in the environment.")
        sys.exit(1)
    if not INFLUX_ORG:
        logger.error("Missing InfluxDB org. Set INFLUX_ORG in the environment.")
        sys.exit(1)
    if not INFLUX_BUCKET:
        logger.error("Missing InfluxDB bucket. Set INFLUX_BUCKET in the environment.")
        sys.exit(1)


def flight_state_name(state: int) -> str:
    """Convert FlightState enum to string."""
    state_names = {
        FlightState.STANDBY: "STANDBY",
        FlightState.ASCENT: "ASCENT",
        FlightState.MACH_LOCK: "MACH_LOCK",
        FlightState.DROGUE_DESCENT: "DROGUE_DESCENT",
        FlightState.MAIN_DESCENT: "MAIN_DESCENT",
        FlightState.LANDED: "LANDED",
    }
    return state_names.get(state, f"UNKNOWN_{state}")


def write_telemetry_to_influxdb(write_api, telemetry: TelemetryPacket) -> None:
    """Write TelemetryPacket data to InfluxDB using Point API."""
    try:
        # Create Point object with telemetry measurement
        point = (
            Point("telemetry")
            .tag("flight_state", flight_state_name(telemetry.state))
            .tag("source", "Helios.FALCON.Telemetry")
            # Packet metadata
            .field("counter", telemetry.counter)
            .field("timestamp_ms", telemetry.timestamp_ms)
            .field("state", int(telemetry.state))
            # IMU data
            .field("accel_x", telemetry.accel_x)
            .field("accel_y", telemetry.accel_y)
            .field("accel_z", telemetry.accel_z)
            .field("gyro_x", telemetry.gyro_x)
            .field("gyro_y", telemetry.gyro_y)
            .field("gyro_z", telemetry.gyro_z)
            # Kalman filter estimates
            .field("kf_altitude", telemetry.kf_altitude)
            .field("kf_velocity", telemetry.kf_velocity)
            .field("kf_alt_variance", telemetry.kf_alt_variance)
            .field("kf_vel_variance", telemetry.kf_vel_variance)
            # Barometer 0 data
            .field("baro0_healthy", int(telemetry.baro0_healthy))
            .field("baro0_pressure", telemetry.baro0_pressure)
            .field("baro0_temperature", telemetry.baro0_temperature)
            .field("baro0_altitude", telemetry.baro0_altitude)
            .field("baro0_nis", telemetry.baro0_nis)
            .field("baro0_faults", telemetry.baro0_faults)
            # Barometer 1 data
            .field("baro1_healthy", int(telemetry.baro1_healthy))
            .field("baro1_pressure", telemetry.baro1_pressure)
            .field("baro1_temperature", telemetry.baro1_temperature)
            .field("baro1_altitude", telemetry.baro1_altitude)
            .field("baro1_nis", telemetry.baro1_nis)
            .field("baro1_faults", telemetry.baro1_faults)
            # GPS data
            .field("gps_latitude", telemetry.gps_latitude)
            .field("gps_longitude", telemetry.gps_longitude)
            .field("gps_altitude", telemetry.gps_altitude)
            .field("gps_speed", telemetry.gps_speed)
            .field("gps_sats", int(telemetry.gps_sats))
            .field("gps_fix", int(telemetry.gps_fix))
            .time(datetime.utcnow(), WritePrecision.NS)
        )

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        logger.debug(f"Telemetry point written: counter={telemetry.counter}")

    except Exception as e:
        logger.error(f"Failed to write telemetry to InfluxDB: {e}", exc_info=True)


async def main() -> None:
    validate_influx_config()

    logger.info(
        "Connecting to InfluxDB with url=%s org=%s bucket=%s",
        INFLUX_URL,
        INFLUX_ORG,
        INFLUX_BUCKET,
    )

    # Initialize InfluxDB client
    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
    
    # Initialize Helios client
    helios_client = HeliosClient(
        core_address="Helios",
        core_port=5000,
        node_uri="Helios.FALCON.Dashboard",
    )

    try:
        await helios_client.connect()
        logger.info("Connected to Helios core")

        async with helios_client.subscribe_event(
            address="Helios.FALCON.Telemetry",
            event_name="telemetry",
        ) as events:
            async for event in events:
                if not event.data or len(event.data) < 15: # Increased threshold
                    continue
                try:
                    
                    # Parse incoming data as TelemetryPacket from protobuf schema
                    telemetry = TelemetryPacket().parse(event.data)

                    packet_dict = telemetry.to_dict()
                    print(f"\n--- FULL PACKET [Counter: {telemetry.counter}] ---")
                    for field, value in packet_dict.items():
                        print(f"{field}: {value} ({type(value).__name__})")
                    print("-------------------------------------------\n")

                    # If parsing goes sideways and creates a list, skip this packet
                    if isinstance(telemetry.gyro_y, list):
                        logger.warning(f"Corrupted packet (Field is list): counter={getattr(telemetry, 'counter', 'unknown')}")
                        continue
                    
                    # Write to InfluxDB using Point API
                    write_telemetry_to_influxdb(write_api, telemetry)
                    
                    logger.info(
                        f"[{datetime.now()}] → Telemetry: counter={telemetry.counter}, "
                        f"state={flight_state_name(telemetry.state)}, "
                        f"altitude={telemetry.kf_altitude:.2f}m, "
                        f"velocity={telemetry.kf_velocity:.2f}m/s"
                    )
                    
                except EOFError as e:
                    logger.error(f"Skipping malformed packet: {e}")
                except Exception as e:
                    logger.error(f"Error processing event: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        influx_client.close()
        await helios_client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())