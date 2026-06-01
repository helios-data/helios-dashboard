import logging
import re
from datetime import datetime, timezone

from helios import HeliosClient
from influxdb_client import Point, WritePrecision
from influxdb_client.client.write_api import WriteApi

logger = logging.getLogger(__name__)

_POS_RE = re.compile(
    r"(\d{4}\.\d+)([NS])"   # latitude DDMM.mm + N/S
    r"[/\\]."                # symbol table + symbol
    r"(\d{5}\.\d+)([EW])"   # longitude DDDMM.mm + E/W
)
_ALT_RE = re.compile(r"/A=(\d+)")  # altitude in feet


def _aprs_coord_to_decimal(coord: str, direction: str) -> float:
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
    info = raw.split(":", 1)[1] if ":" in raw else raw

    match = _POS_RE.search(info)
    if not match:
        return None

    lat_str, lat_dir, lon_str, lon_dir = match.groups()

    altitude_m: float | None = None
    alt_match = _ALT_RE.search(info)
    if alt_match:
        altitude_m = int(alt_match.group(1)) * 0.3048  # feet → metres

    return {
        "callsign": callsign,
        "gps_latitude": _aprs_coord_to_decimal(lat_str, lat_dir),
        "gps_longitude": _aprs_coord_to_decimal(lon_str, lon_dir),
        "gps_altitude": altitude_m,
    }


def _write(write_api: WriteApi, bucket: str, org: str, parsed: dict, verbose: bool) -> None:
    point = (
        Point("aprs")
        .tag("source", "APRS")
        .tag("callsign", parsed["callsign"])
        .field("gps_latitude", parsed["gps_latitude"])
        .field("gps_longitude", parsed["gps_longitude"])
        .time(datetime.now(timezone.utc), WritePrecision.NS)
    )
    if parsed["gps_altitude"] is not None:
        point = point.field("gps_altitude", parsed["gps_altitude"])

    write_api.write(bucket=bucket, org=org, record=point)

    if verbose:
        logger.debug(
            "APRS point written: callsign=%s lat=%.5f lon=%.5f",
            parsed["callsign"],
            parsed["gps_latitude"],
            parsed["gps_longitude"],
        )


async def run(write_api: WriteApi, bucket: str, org: str, verbose: bool = False) -> None:
    """Subscribe to Helios.APRS.Receiver and forward position data to InfluxDB."""
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
                    if verbose:
                        logger.debug("Raw APRS packet: %s", raw)

                    parsed = parse_aprs_packet(raw)
                    if parsed is None:
                        logger.warning("No position in APRS packet: %r", raw)
                        continue

                    _write(write_api, bucket, org, parsed, verbose)

                    if not verbose:
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
        await helios_client.disconnect()
