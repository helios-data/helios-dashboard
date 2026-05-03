import asyncio
import time
import logging

from helios import HeliosClient
from influxdb_client import InfluxDBClient
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


def write_to_influxdb(client, measurement: str, fields: dict, tags: dict = None):
    """Write data point to InfluxDB."""
    try:
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        # Build the line protocol
        tag_str = ""
        if tags:
            tag_str = "," + ",".join(f"{k}={v}" for k, v in tags.items())
        
        field_str = ",".join(f'{k}={v}' for k, v in fields.items())
        line = f"{measurement}{tag_str} {field_str} {int(time.time() * 1e9)}"
        
        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=line)
        logger.debug(f"Wrote to InfluxDB: {line}")
    except Exception as e:
        logger.error(f"Failed to write to InfluxDB: {e}")


async def main() -> None:
    # Initialize InfluxDB client
    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    
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
                    # Parse incoming data as TelemetryPacket
                    telemetry = TelemetryPacket().parse(event.data)
                    
                    # Extract fields for InfluxDB
                    fields = {
                        "counter": telemetry.counter,
                        "timestamp_ms": telemetry.timestamp_ms,
                        "state": int(telemetry.state),
                        "accel_x": telemetry.accel_x,
                        "accel_y": telemetry.accel_y,
                        "accel_z": telemetry.accel_z,
                        "gyro_x": telemetry.gyro_x,
                        "gyro_y": telemetry.gyro_y,
                        "gyro_z": telemetry.gyro_z,
                        "kf_altitude": telemetry.kf_altitude,
                        "kf_velocity": telemetry.kf_velocity,
                        "kf_alt_variance": telemetry.kf_alt_variance,
                        "kf_vel_variance": telemetry.kf_vel_variance,
                        "baro0_pressure": telemetry.baro0_pressure,
                        "baro0_temperature": telemetry.baro0_temperature,
                        "baro0_altitude": telemetry.baro0_altitude,
                        "baro0_nis": telemetry.baro0_nis,
                        "baro0_faults": telemetry.baro0_faults,
                        "baro1_pressure": telemetry.baro1_pressure,
                        "baro1_temperature": telemetry.baro1_temperature,
                        "baro1_altitude": telemetry.baro1_altitude,
                        "baro1_nis": telemetry.baro1_nis,
                        "baro1_faults": telemetry.baro1_faults,
                    }
                    
                    # Add boolean flags as integers (InfluxDB compatible)
                    fields["baro0_healthy"] = int(telemetry.baro0_healthy)
                    fields["baro1_healthy"] = int(telemetry.baro1_healthy)
                    
                    # Write to InfluxDB with flight state tag
                    write_to_influxdb(
                        influx_client,
                        "telemetry",
                        fields,
                        tags={"flight_state": flight_state_name(telemetry.state)}
                    )
                    
                    logger.info(
                        f"Telemetry: counter={telemetry.counter}, "
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