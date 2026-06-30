-- ============================================================================
-- schema.sql  —  Normalized (3NF) relational schema for a GTFS public-transit feed
-- Target: SQLite 3.  Run this script once to (re)create all tables.
--
-- Design notes
-- ------------
-- * GTFS is already close to 3NF. This schema makes the relationships explicit
--   with PRIMARY KEY / FOREIGN KEY constraints and pulls two repeating enum
--   fields (route_type, exception_type) out into small LOOKUP tables so their
--   meaning is stored once, not repeated as magic numbers on every row.
-- * Clock times are stored as zero-padded TEXT 'HH:MM:SS'. GTFS allows values
--   past 24:00:00 for trips after midnight, so a TIME/DATETIME type is unsuitable.
-- * Service dates are stored as TEXT 'YYYYMMDD', matching the GTFS calendar format.
-- ============================================================================

-- Drop in reverse dependency order so the script is idempotent.
DROP TABLE IF EXISTS fare_rules;
DROP TABLE IF EXISTS fare_attributes;
DROP TABLE IF EXISTS frequencies;
DROP TABLE IF EXISTS stop_times;
DROP TABLE IF EXISTS trips;
DROP TABLE IF EXISTS calendar_dates;
DROP TABLE IF EXISTS exception_type;
DROP TABLE IF EXISTS calendar;
DROP TABLE IF EXISTS shapes;
DROP TABLE IF EXISTS stops;
DROP TABLE IF EXISTS routes;
DROP TABLE IF EXISTS route_type;
DROP TABLE IF EXISTS agency;

-- ----------------------------------------------------------------------------
-- Reference / lookup tables (normalization of enum codes)
-- ----------------------------------------------------------------------------
CREATE TABLE route_type (
    route_type_id  INTEGER PRIMARY KEY,   -- GTFS route_type code (0,1,2,3,...)
    description    TEXT NOT NULL          -- e.g. 'Bus', 'Subway', 'Rail'
);

CREATE TABLE exception_type (
    exception_type_id INTEGER PRIMARY KEY, -- 1 = service added, 2 = service removed
    description       TEXT NOT NULL
);

-- ----------------------------------------------------------------------------
-- Core entities
-- ----------------------------------------------------------------------------
CREATE TABLE agency (
    agency_id        TEXT PRIMARY KEY,
    agency_name      TEXT NOT NULL,
    agency_url       TEXT,
    agency_timezone  TEXT,
    agency_lang      TEXT,
    agency_phone     TEXT
);

CREATE TABLE routes (
    route_id          TEXT PRIMARY KEY,
    agency_id         TEXT REFERENCES agency(agency_id),
    route_short_name  TEXT,
    route_long_name   TEXT,
    route_desc        TEXT,
    route_type        INTEGER REFERENCES route_type(route_type_id),
    route_url         TEXT,
    route_color       TEXT,
    route_text_color  TEXT
);

CREATE TABLE stops (
    stop_id    TEXT PRIMARY KEY,
    stop_name  TEXT NOT NULL,
    stop_desc  TEXT,
    stop_lat   REAL,
    stop_lon   REAL,
    zone_id    TEXT,
    stop_url   TEXT
);

CREATE TABLE shapes (
    shape_id            TEXT NOT NULL,
    shape_pt_lat        REAL,
    shape_pt_lon        REAL,
    shape_pt_sequence   INTEGER NOT NULL,
    shape_dist_traveled REAL,
    PRIMARY KEY (shape_id, shape_pt_sequence)
);

CREATE TABLE calendar (
    service_id  TEXT PRIMARY KEY,
    monday      INTEGER NOT NULL CHECK (monday    IN (0,1)),
    tuesday     INTEGER NOT NULL CHECK (tuesday   IN (0,1)),
    wednesday   INTEGER NOT NULL CHECK (wednesday IN (0,1)),
    thursday    INTEGER NOT NULL CHECK (thursday  IN (0,1)),
    friday      INTEGER NOT NULL CHECK (friday    IN (0,1)),
    saturday    INTEGER NOT NULL CHECK (saturday  IN (0,1)),
    sunday      INTEGER NOT NULL CHECK (sunday    IN (0,1)),
    start_date  TEXT,   -- 'YYYYMMDD'
    end_date    TEXT
);

CREATE TABLE calendar_dates (
    service_id      TEXT NOT NULL REFERENCES calendar(service_id),
    date            TEXT NOT NULL,   -- 'YYYYMMDD'
    exception_type  INTEGER REFERENCES exception_type(exception_type_id),
    PRIMARY KEY (service_id, date)
);

CREATE TABLE trips (
    trip_id        TEXT PRIMARY KEY,
    route_id       TEXT NOT NULL REFERENCES routes(route_id),
    service_id     TEXT NOT NULL REFERENCES calendar(service_id),
    trip_headsign  TEXT,
    direction_id   INTEGER CHECK (direction_id IN (0,1)),
    block_id       TEXT,
    shape_id       TEXT
);

CREATE TABLE stop_times (
    trip_id         TEXT NOT NULL REFERENCES trips(trip_id),
    stop_id         TEXT NOT NULL REFERENCES stops(stop_id),
    stop_sequence   INTEGER NOT NULL,
    arrival_time    TEXT,   -- zero-padded 'HH:MM:SS', may exceed 24:00:00
    departure_time  TEXT,
    stop_headsign   TEXT,
    pickup_type     INTEGER,
    drop_off_type   INTEGER,
    PRIMARY KEY (trip_id, stop_sequence)
);

CREATE TABLE frequencies (
    trip_id       TEXT NOT NULL REFERENCES trips(trip_id),
    start_time    TEXT NOT NULL,
    end_time      TEXT,
    headway_secs  INTEGER,
    PRIMARY KEY (trip_id, start_time)
);

CREATE TABLE fare_attributes (
    fare_id           TEXT PRIMARY KEY,
    price             REAL,
    currency_type     TEXT,
    payment_method    INTEGER,
    transfers         INTEGER,
    transfer_duration INTEGER
);

CREATE TABLE fare_rules (
    fare_id        TEXT NOT NULL REFERENCES fare_attributes(fare_id),
    route_id       TEXT REFERENCES routes(route_id),
    origin_id      TEXT,
    destination_id TEXT,
    contains_id    TEXT,
    PRIMARY KEY (fare_id, route_id)
);

-- Helpful secondary indexes for the analytical queries.
CREATE INDEX idx_trips_route       ON trips(route_id);
CREATE INDEX idx_stop_times_trip   ON stop_times(trip_id);
CREATE INDEX idx_stop_times_stop   ON stop_times(stop_id);
