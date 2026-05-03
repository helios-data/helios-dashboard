import asyncio
import logging
from datetime import datetime

from helios import HeliosClient
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from generated import TelemetryPacket, FlightState

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# InfluxDB configuration
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "my-super-token"
INFLUX_ORG = "rocket"
INFLUX_BUCKET = "mock_data"


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
            .time(datetime.utcnow(), WritePrecision.NS)
        )

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        logger.debug(f"Telemetry point written: counter={telemetry.counter}")

    except Exception as e:
        logger.error(f"Failed to write telemetry to InfluxDB: {e}", exc_info=True)


async def main() -> None:
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
                try:
                    # Parse incoming data as TelemetryPacket from protobuf schema
                    telemetry = TelemetryPacket().parse(event.data)
                    
                    # Write to InfluxDB using Point API
                    write_telemetry_to_influxdb(write_api, telemetry)
                    
                    logger.info(
                        f"[{datetime.now()}] → Telemetry: counter={telemetry.counter}, "
                        f"state={flight_state_name(telemetry.state)}, "
                        f"altitude={telemetry.kf_altitude:.2f}m, "
                        f"velocity={telemetry.kf_velocity:.2f}m/s"
                    )
                    
                except Exception as e:
                    logger.error(f"Error processing event: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        influx_client.close()
        await helios_client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())