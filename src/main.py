import asyncio
import logging
import os
import sys
import threading # signal is not portable to windows
from datetime import datetime, timezone

from helios import HeliosClient
from helios.generated.helios.transport import AprsPacket
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS, WriteApi
from generated import TelemetryPacket, FlightState

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# InfluxDB configuration
INFLUX_URL = os.getenv("INFLUX_URL", "http://127.0.0.1:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "my-super-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "rocket")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "mock_data")
VERBOSE: bool = os.getenv("VERBOSE", "") != ""
STANDALONE: bool = os.getenv("STANDALONE", "") != ""


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
    state_names = {
        FlightState.STANDBY: "STANDBY",
        FlightState.ASCENT: "ASCENT",
        FlightState.MACH_LOCK: "MACH_LOCK",
        FlightState.DROGUE_DESCENT: "DROGUE_DESCENT",
        FlightState.MAIN_DESCENT: "MAIN_DESCENT",
        FlightState.LANDED: "LANDED",
    }
    return state_names.get(state, f"UNKNOWN_{state}")


def write_telemetry_to_influxdb(write_api: WriteApi, telemetry: TelemetryPacket) -> None:
    try:
        point = (
            Point("telemetry")
            .tag("flight_state", flight_state_name(telemetry.state))
            .tag("source", "Helios.FALCON.Telemetry")
            # Packet metadata
            .field("counter", telemetry.counter)
            .field("timestamp_ms", telemetry.timestamp_ms)
            .field("state", int(telemetry.state))
            # IMU data
            .field("accel_x", float(telemetry.accel_x))
            .field("accel_y", float(telemetry.accel_y))
            .field("accel_z", float(telemetry.accel_z))
            .field("gyro_x", float(telemetry.gyro_x))
            .field("gyro_y", float(telemetry.gyro_y))
            .field("gyro_z", float(telemetry.gyro_z))
            # Kalman filter estimates
            .field("kf_altitude", float(telemetry.kf_altitude))
            .field("kf_velocity", float(telemetry.kf_velocity))
            .field("kf_alt_variance", float(telemetry.kf_alt_variance))
            .field("kf_vel_variance", float(telemetry.kf_vel_variance))
            # Barometer 0 data
            .field("baro0_healthy", int(telemetry.baro0_healthy))
            .field("baro0_pressure", float(telemetry.baro0_pressure))
            .field("baro0_temperature", float(telemetry.baro0_temperature))
            .field("baro0_altitude", float(telemetry.baro0_altitude))
            .field("baro0_nis", float(telemetry.baro0_nis))
            .field("baro0_faults", telemetry.baro0_faults)
            # Barometer 1 data
            .field("baro1_healthy", int(telemetry.baro1_healthy))
            .field("baro1_pressure", float(telemetry.baro1_pressure))
            .field("baro1_temperature", float(telemetry.baro1_temperature))
            .field("baro1_altitude", float(telemetry.baro1_altitude))
            .field("baro1_nis", float(telemetry.baro1_nis))
            .field("baro1_faults", telemetry.baro1_faults)
            # GPS data
            .field("gps_latitude", float(telemetry.gps_latitude))
            .field("gps_longitude", float(telemetry.gps_longitude))
            .field("gps_altitude", float(telemetry.gps_altitude))
            .field("gps_speed", float(telemetry.gps_speed))
            .field("gps_sats", int(telemetry.gps_sats))
            .field("gps_fix", int(telemetry.gps_fix))
            .time(datetime.now(timezone.utc), WritePrecision.NS)
        )

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        if VERBOSE:
            logger.debug(f"Telemetry point written: counter={telemetry.counter}")

    except Exception as e:
        logger.error(f"Failed to write telemetry to InfluxDB: {e}", exc_info=True)


def write_aprs_to_influxdb(write_api: WriteApi, packet: AprsPacket) -> None:
    try:
        pos = packet.position
        assert pos is not None
        point = (
            Point("aprs")
            .tag("source", "APRS")
            .tag("callsign", packet.source)
            .field("gps_latitude", pos.latitude)
            .field("gps_longitude", pos.longitude)
            .time(datetime.now(timezone.utc), WritePrecision.NS)
        )
        if pos.altitude_ft is not None:
            point = point.field("gps_altitude", pos.altitude_ft * 0.3048)  # feet → metres

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)
        if VERBOSE:
            logger.debug(
                "APRS point written: callsign=%s lat=%.5f lon=%.5f",
                packet.source,
                pos.latitude,
                pos.longitude,
            )

    except Exception as e:
        logger.error(f"Failed to write APRS to InfluxDB: {e}", exc_info=True)


async def process_telemetry(events, write_api: WriteApi) -> None:
    async for event in events:
        if not event.data or len(event.data) < 15:
            continue
        try:
            telemetry = TelemetryPacket().parse(event.data)

            packet_dict = telemetry.to_dict()
            if VERBOSE:
                print(f"\n--- FULL PACKET [Counter: {telemetry.counter}] ---")
                for field, value in packet_dict.items():
                    print(f"{field}: {value} ({type(value).__name__})")
                print("-------------------------------------------\n")

            if any(isinstance(v, list) for v in packet_dict.values()):
                logger.warning(f"Corrupted packet (List field): counter={getattr(telemetry, 'counter', 'unknown')}")
                continue

            lat, lon = float(telemetry.gps_latitude), float(telemetry.gps_longitude)
            if lat == int(lat) or lon == int(lon):
                logger.warning(
                    "Ignoring telemetry packet counter=%s: integer lat/lon (lat=%.5f lon=%.5f)",
                    telemetry.counter,
                    lat,
                    lon,
                )
                continue

            write_telemetry_to_influxdb(write_api, telemetry)

            if not VERBOSE:
                logger.info(
                    f"[{datetime.now()}] → Telemetry: counter={telemetry.counter}, "
                    f"state={flight_state_name(telemetry.state)}, "
                    f"altitude={telemetry.kf_altitude:.2f}m, "
                    f"velocity={telemetry.kf_velocity:.2f}m/s"
                )

        except EOFError as e:
            logger.error(f"Skipping malformed packet: {e}")
        except Exception as e:
            logger.error(f"Error processing telemetry event: {e}", exc_info=True)


async def process_aprs(events, write_api: WriteApi) -> None:
    async for event in events:
        if not event.data:
            continue
        try:
            packet = AprsPacket().parse(event.data)

            pos = packet.position
            if pos is None:
                logger.warning("No position in APRS packet from %s", packet.source)
                continue

            if pos.latitude == int(pos.latitude) or pos.longitude == int(pos.longitude):
                logger.warning(
                    "Ignoring APRS packet from %s: integer lat/lon (lat=%.5f lon=%.5f)",
                    packet.source,
                    pos.latitude,
                    pos.longitude,
                )
                continue

            write_aprs_to_influxdb(write_api, packet)

            if not VERBOSE:
                logger.info(
                    "[%s] → APRS: callsign=%s lat=%.5f lon=%.5f",
                    datetime.now(),
                    packet.source,
                    pos.latitude,
                    pos.longitude,
                )

        except Exception as e:
            logger.error("Error processing APRS event: %s", e, exc_info=True)


async def dashboard_task(write_api: WriteApi) -> None:
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
        ) as telemetry_events:
            async with helios_client.subscribe_event(
                address="Helios.Services.TeleGPS",
                event_name="aprs",
            ) as aprs_events:
                await asyncio.gather(
                    process_telemetry(telemetry_events, write_api),
                    process_aprs(aprs_events, write_api),
                )

    except Exception as e:
        logger.error(f"Fatal error in dashboard task: {e}", exc_info=True)
    finally:
        await helios_client.disconnect()


async def main() -> None:
    validate_influx_config()

    logger.info(
        "Connecting to InfluxDB with url=%s org=%s bucket=%s",
        INFLUX_URL,
        INFLUX_ORG,
        INFLUX_BUCKET,
    )

    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)

    if STANDALONE:
        try:
            logger.info("Running in standalone mode")
            threading.Event().wait()
        except KeyboardInterrupt:
            logger.info("Shutting down")
        finally:
            influx_client.close()
            sys.exit(0)

    try:
        await dashboard_task(write_api)
    finally:
        influx_client.close()


if __name__ == "__main__":
    asyncio.run(main())
