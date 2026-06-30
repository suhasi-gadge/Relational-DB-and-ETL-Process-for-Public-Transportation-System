#!/usr/bin/env python3
"""
etl.py  —  Extract / Transform / Load a public GTFS transit feed into SQLite.

EXTRACT   : download the official GTFS example feed (a .zip of CSV "*.txt" files).
TRANSFORM : normalize column names/types, zero-pad clock times, seed lookup tables.
LOAD      : create the schema from schema.sql and insert rows in FK-safe order.

Run:
    python etl.py            # builds gtfs.db and prints a verification report

The script is idempotent: schema.sql drops and recreates every table, so re-running
produces a clean database.
"""

import io
import sqlite3
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

# Official, publicly available GTFS example feed (Google "transit" repository).
FEED_URL = (
    "https://raw.githubusercontent.com/google/transit/master/"
    "gtfs/spec/en/examples/sample-feed-1.zip"
)
HERE = Path(__file__).parent
DB_PATH = HERE / "gtfs.db"
SCHEMA_PATH = HERE / "schema.sql"

# GTFS standard route_type codes -> human-readable description (lookup seed).
ROUTE_TYPES = [
    (0, "Tram / Light rail"), (1, "Subway / Metro"), (2, "Rail"),
    (3, "Bus"), (4, "Ferry"), (5, "Cable tram"), (6, "Aerial lift"),
    (7, "Funicular"), (11, "Trolleybus"), (12, "Monorail"),
]
EXCEPTION_TYPES = [(1, "Service added"), (2, "Service removed")]


# ---------------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------------
def extract(url: str) -> dict[str, pd.DataFrame]:
    """Download the GTFS zip and return {filename_stem: DataFrame} for each .txt."""
    print(f"[extract] downloading feed: {url}")
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        sys.exit(f"[extract] ERROR: could not download feed: {exc}")

    feed: dict[str, pd.DataFrame] = {}
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for name in zf.namelist():
            if not name.endswith(".txt"):
                continue
            with zf.open(name) as fh:
                # dtype=str keeps IDs/codes intact; we coerce types in transform.
                df = pd.read_csv(fh, dtype=str, skipinitialspace=True)
            feed[Path(name).stem] = df
            print(f"[extract]   {name:<20} {len(df):>4} rows")
    return feed


# ---------------------------------------------------------------------------
# TRANSFORM helpers
# ---------------------------------------------------------------------------
def pad_time(val):
    """Zero-pad a GTFS clock string to 'HH:MM:SS' so text sorting is correct.

    GTFS times are not zero-padded (e.g. '6:00:00') and may exceed 24:00:00 for
    after-midnight trips, so we pad the hour rather than parse to a real time.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
        return None
    parts = str(val).split(":")
    if len(parts) != 3:
        return val
    h, m, s = parts
    return f"{int(h):02d}:{m}:{s}"


def to_rows(df: pd.DataFrame, columns, int_cols=(), real_cols=()):
    """Align a DataFrame to `columns`, coerce types, and return clean tuples.

    Missing columns are filled with NULL; numeric columns are coerced; pandas
    NaN/NA values are converted to Python None for SQLite.
    """
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            df[col] = None
    df = df[list(columns)]
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in real_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    def clean(v):
        if v is None:
            return None
        try:
            if pd.isna(v):
                return None
        except (TypeError, ValueError):
            pass
        return v

    return [tuple(clean(v) for v in row)
            for row in df.itertuples(index=False, name=None)]


def insert(conn, table, columns, rows):
    """Parameterized bulk insert; FK constraints are enforced on the connection."""
    placeholders = ",".join("?" * len(columns))
    conn.executemany(
        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({placeholders})", rows
    )
    print(f"[load]    {table:<16} +{len(rows):>4} rows")


# ---------------------------------------------------------------------------
# TRANSFORM + LOAD
# ---------------------------------------------------------------------------
def load(conn, feed: dict[str, pd.DataFrame]) -> None:
    # Build the empty normalized schema.
    conn.executescript(SCHEMA_PATH.read_text())

    # --- seed lookup tables -------------------------------------------------
    insert(conn, "route_type", ("route_type_id", "description"), ROUTE_TYPES)
    insert(conn, "exception_type", ("exception_type_id", "description"),
           EXCEPTION_TYPES)

    # --- agency -------------------------------------------------------------
    cols = ("agency_id", "agency_name", "agency_url", "agency_timezone",
            "agency_lang", "agency_phone")
    insert(conn, "agency", cols, to_rows(feed["agency"], cols))

    # --- routes -------------------------------------------------------------
    cols = ("route_id", "agency_id", "route_short_name", "route_long_name",
            "route_desc", "route_type", "route_url", "route_color",
            "route_text_color")
    insert(conn, "routes", cols,
           to_rows(feed["routes"], cols, int_cols=("route_type",)))

    # --- stops --------------------------------------------------------------
    cols = ("stop_id", "stop_name", "stop_desc", "stop_lat", "stop_lon",
            "zone_id", "stop_url")
    insert(conn, "stops", cols,
           to_rows(feed["stops"], cols, real_cols=("stop_lat", "stop_lon")))

    # --- shapes (optional; the example feed has none) -----------------------
    if "shapes" in feed and len(feed["shapes"]):
        cols = ("shape_id", "shape_pt_lat", "shape_pt_lon",
                "shape_pt_sequence", "shape_dist_traveled")
        insert(conn, "shapes", cols,
               to_rows(feed["shapes"], cols,
                       int_cols=("shape_pt_sequence",),
                       real_cols=("shape_pt_lat", "shape_pt_lon",
                                  "shape_dist_traveled")))

    # --- calendar -----------------------------------------------------------
    cols = ("service_id", "monday", "tuesday", "wednesday", "thursday",
            "friday", "saturday", "sunday", "start_date", "end_date")
    days = cols[1:8]
    insert(conn, "calendar", cols,
           to_rows(feed["calendar"], cols, int_cols=days))

    # --- calendar_dates -----------------------------------------------------
    if "calendar_dates" in feed and len(feed["calendar_dates"]):
        cols = ("service_id", "date", "exception_type")
        insert(conn, "calendar_dates", cols,
               to_rows(feed["calendar_dates"], cols,
                       int_cols=("exception_type",)))

    # --- trips --------------------------------------------------------------
    cols = ("trip_id", "route_id", "service_id", "trip_headsign",
            "direction_id", "block_id", "shape_id")
    insert(conn, "trips", cols,
           to_rows(feed["trips"], cols, int_cols=("direction_id",)))

    # --- stop_times (TRANSFORM: zero-pad times; handle 'drop_off' variants) --
    st = feed["stop_times"].copy()
    # The example feed mislabels the drop-off column 'drop_off_time'; normalize it.
    if "drop_off_time" in st.columns and "drop_off_type" not in st.columns:
        st = st.rename(columns={"drop_off_time": "drop_off_type"})
    st["arrival_time"] = st["arrival_time"].map(pad_time)
    st["departure_time"] = st["departure_time"].map(pad_time)
    cols = ("trip_id", "stop_id", "stop_sequence", "arrival_time",
            "departure_time", "stop_headsign", "pickup_type", "drop_off_type")
    insert(conn, "stop_times", cols,
           to_rows(st, cols,
                   int_cols=("stop_sequence", "pickup_type", "drop_off_type")))

    # --- frequencies (TRANSFORM: zero-pad start/end times) ------------------
    if "frequencies" in feed and len(feed["frequencies"]):
        fq = feed["frequencies"].copy()
        fq["start_time"] = fq["start_time"].map(pad_time)
        fq["end_time"] = fq["end_time"].map(pad_time)
        cols = ("trip_id", "start_time", "end_time", "headway_secs")
        insert(conn, "frequencies", cols,
               to_rows(fq, cols, int_cols=("headway_secs",)))

    # --- fares --------------------------------------------------------------
    if "fare_attributes" in feed and len(feed["fare_attributes"]):
        cols = ("fare_id", "price", "currency_type", "payment_method",
                "transfers", "transfer_duration")
        insert(conn, "fare_attributes", cols,
               to_rows(feed["fare_attributes"], cols,
                       int_cols=("payment_method", "transfers",
                                 "transfer_duration"),
                       real_cols=("price",)))
    if "fare_rules" in feed and len(feed["fare_rules"]):
        cols = ("fare_id", "route_id", "origin_id", "destination_id",
                "contains_id")
        insert(conn, "fare_rules", cols, to_rows(feed["fare_rules"], cols))

    conn.commit()


# ---------------------------------------------------------------------------
# VERIFY
# ---------------------------------------------------------------------------
def verify(conn) -> None:
    """Check referential integrity and print per-table row counts."""
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        sys.exit(f"[verify] FK violations found: {violations}")
    print("[verify] foreign-key check passed (referential integrity OK)")

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print("\n[verify] row counts:")
    for t in tables:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"           {t:<18} {n:>4}")


def main() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")   # enforce relationships on insert
    try:
        load(conn, extract(FEED_URL))
        verify(conn)
        print(f"\n[done] database written to {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
