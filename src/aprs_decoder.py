import asyncio
import logging
import os
import re
import sys
from datetime import datetime

from helios import HeliosClient
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INFLUX_URL = os.getenv("INFLUX_URL", "http://127.0.0.1:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "my-super-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "rocket")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "mock_data")
VERBOSE: bool = os.getenv("VERBOSE", "") != ""

# APRS uncompressed position: DDMMSSssN/DDDMMSSssW (with optional symbol/altitude)
# Supports: !DDMM.mmN/DDDMM.mmW  =DDMM.mmN/DDDMM.mmW  @...hDDMM.mmN/DDDMM.mmW
_POS_RE = re.compile(
    r"(\d{4}\.\d+)([NS])"   # latitude DDMM.mm + N/S
    r"[/\\]."                # symbol table + symbol (one char each)
    r"(\d{5}\.\d+)([EW])"   # longitude DDDMM.mm + E/W
)
_ALT_RE = re.compile(r"/A=(\d+)")  # altitude in feet


def _aprs_coord_to_decimal(coord: str, direction: str) -> float:
    """Convert APRS DDMM.mm / DDDMM.mm string to decimal degrees."""
    dot = coord.index(".")
    deg_end = dot - 2
    degrees = int(coord[:deg_end])
    minutes = float(coord[deg_end:])
    decimal = degrees + minutes / 60.0
    if direction in ("S", "W"):
        decimal = -decimal
    return decimal


def parse_aprs_packet(raw: str) -> dict | None:
    """
    Parse a raw APRS packet string and return position data, or None if no
    position report is present.

    Returned dict keys: callsign, gps_latitude, gps_longitude, gps_altitude
    (gps_altitude is None when not present in the packet).
    """
    callsign = raw.split(">")[0].strip() if ">" in raw else "UNKNOWN"

    # Isolate the information field (everything after the first ':')
    info = raw.split(":", 1)[1] if ":" in raw else raw

    match = _POS_RE.search(info)
    if not match:
        return None

    lat_str, lat_dir, lon_str, lon_dir = match.groups()
    latitude = _aprs_coord_to_decimal(lat_str, lat_dir)
    longitude = _aprs_coord_to_decimal(lon_str, lon_dir)

    altitude_m: float | None = None
    alt_match = _ALT_RE.search(info)
    if alt_match:
        altitude_m = int(alt_match.group(1)) * 0.3048  # feet → metres

    return {
        "callsign": callsign,
        "gps_latitude": latitude,
        "gps_longitude": longitude,
        "gps_altitude": altitude_m,
    }


def write_aprs_to_influxdb(write_api, parsed: dict) -> None:
    try:
        point = (
            Point("aprs")
            .tag("source", "APRS")
            .tag("callsign", parsed["callsign"])
            .field("gps_latitude", parsed["gps_latitude"])
            .field("gps_longitude", parsed["gps_longitude"])
            .time(datetime.utcnow(), WritePrecision.NS)
        )
        if parsed["gps_altitude"] is not None:
            point = point.field("gps_altitude", parsed["gps_altitude"])

        write_api.write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)

        if VERBOSE:
            logger.debug(
                "APRS point written: callsign=%s lat=%.5f lon=%.5f",
                parsed["callsign"],
                parsed["gps_latitude"],
                parsed["gps_longitude"],
            )
    except Exception as e:
        logger.error("Failed to write APRS data to InfluxDB: %s", e, exc_info=True)


async def main() -> None:
    if not INFLUX_TOKEN:
        logger.error("Missing InfluxDB token. Set INFLUX_TOKEN.")
        sys.exit(1)

    logger.info(
        "APRS decoder connecting to InfluxDB url=%s org=%s bucket=%s",
        INFLUX_URL,
        INFLUX_ORG,
        INFLUX_BUCKET,
    )

    influx_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)

    helios_client = HeliosClient(
        core_address="Helios",
        core_port=5000,
        node_uri="Helios.APRS.Dashboard",
    )

    try:
        await helios_client.connect()
        logger.info("APRS decoder connected to Helios core")

        async with helios_client.subscribe_event(
            address="Helios.APRS.Receiver",
            event_name="aprs",
        ) as events:
            async for event in events:
                if not event.data:
                    continue
                try:
                    raw = event.data.decode("utf-8", errors="replace").strip()

                    if VERBOSE:
                        logger.debug("Raw APRS packet: %s", raw)

                    parsed = parse_aprs_packet(raw)
                    if parsed is None:
                        logger.warning("No position in APRS packet: %r", raw)
                        continue

                    write_aprs_to_influxdb(write_api, parsed)

                    if not VERBOSE:
                        logger.info(
                            "[%s] → APRS: callsign=%s lat=%.5f lon=%.5f",
                            datetime.now(),
                            parsed["callsign"],
                            parsed["gps_latitude"],
                            parsed["gps_longitude"],
                        )
                except Exception as e:
                    logger.error("Error processing APRS event: %s", e, exc_info=True)

    except Exception as e:
        logger.error("Fatal error in APRS decoder: %s", e, exc_info=True)
    finally:
        influx_client.close()
        await helios_client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
