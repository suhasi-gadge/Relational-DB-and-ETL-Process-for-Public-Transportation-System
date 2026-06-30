# GTFS Public-Transit Database — Schema & ETL

A normalized (3NF) relational schema for a public-transportation **GTFS** feed,
plus a Python ETL pipeline that loads a real public dataset into a local SQLite
database, and a set of analytical SQL queries.

---

## Data source

| | |
|---|---|
| **Dataset** | GTFS — *General Transit Feed Specification* example feed |
| **Provider** | Google `transit` repository (public, canonical GTFS sample) |
| **URL** | `https://raw.githubusercontent.com/google/transit/master/gtfs/spec/en/examples/sample-feed-1.zip` |
| **Contents** | agency, routes, stops, trips, stop_times, calendar, calendar_dates, frequencies, fare_attributes, fare_rules |

GTFS is the worldwide standard for publishing transit schedules, so the same
schema and ETL work against any real city/agency feed — point `FEED_URL` in
`etl.py` at another agency's `.zip` to load production data.

---

## Schema design (3NF)

`schema.sql` creates the tables below. GTFS is already close to third normal
form; this schema makes every relationship explicit with primary and foreign
keys and pulls two repeating enum codes into **lookup tables** so their meaning
is stored once instead of as magic numbers on every row.

```
agency ──< routes ──< trips ──< stop_times >── stops
                 │         │
   route_type >──┘         └──< frequencies
                           │
calendar ──< trips         └── (service_id) >── calendar
calendar ──< calendar_dates >── exception_type
fare_attributes ──< fare_rules >── routes
```

**Lookup tables (normalization):**
- `route_type(route_type_id, description)` — GTFS code → `Bus`, `Subway`, `Rail`, …
- `exception_type(exception_type_id, description)` — `1 = Service added`, `2 = Service removed`

**Design choices:**
- Clock times are stored as zero-padded `TEXT 'HH:MM:SS'`. GTFS permits values
  past `24:00:00` for after-midnight trips, so a native time type is unsuitable;
  zero-padding also makes text `MIN`/`MAX`/sorting correct.
- Service dates are `TEXT 'YYYYMMDD'`, matching the GTFS calendar format.
- Composite primary keys model the natural grain: `stop_times(trip_id, stop_sequence)`,
  `calendar_dates(service_id, date)`, `frequencies(trip_id, start_time)`.
- Foreign keys are enforced at load time (`PRAGMA foreign_keys = ON`), and the
  ETL runs `PRAGMA foreign_key_check` afterward to prove referential integrity.

---

## Transformation rules applied by the ETL

1. **Type coercion** — IDs/codes read as text, then numeric fields
   (`route_type`, `direction_id`, `stop_sequence`, `headway_secs`, lat/lon,
   `price`, …) are coerced to INTEGER/REAL; empty strings become SQL `NULL`.
2. **Time normalization** — `arrival_time`, `departure_time`, and frequency
   `start_time`/`end_time` are zero-padded to `HH:MM:SS`.
3. **Column reconciliation** — the example feed mislabels the drop-off column
   `drop_off_time`; the ETL maps it to the schema's `drop_off_type`.
4. **Lookup seeding** — `route_type` and `exception_type` reference tables are
   populated from the GTFS specification before dependent rows load.
5. **FK-safe load order** — parents (agency, routes, stops, calendar) load
   before children (trips, stop_times, frequencies, fares).

---

## Repository structure

```
gtfs-etl/
├── schema.sql        # DDL: normalized 3NF schema (PK/FK, lookups, indexes)
├── etl.py            # Python ETL: extract GTFS zip -> transform -> load SQLite
├── queries.sql       # 5 analytical SQL queries
├── requirements.txt
├── README.md
└── .gitignore        # gtfs.db is generated, not committed
```

---

## How to run

```bash
python -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt

python etl.py                 # downloads feed, builds & populates gtfs.db
sqlite3 gtfs.db < queries.sql # run the analytical queries
```

`etl.py` is idempotent — it recreates every table on each run.

---

## Sample output

`etl.py` populates 13 tables and confirms integrity:

```
[verify] foreign-key check passed (referential integrity OK)
  agency 1 | routes 5 | stops 9 | trips 11 | stop_times 28 | frequencies 11
  calendar 2 | calendar_dates 1 | fare_attributes 2 | fare_rules 4
  route_type 10 | exception_type 2 | shapes 0
```

**Q1 — trips per route (with looked-up route type):**

```
route_id | route_long_name                 | route_type | num_trips
AAMV     | Airport - Amargosa Valley       | Bus        | 4
AB       | Airport - Bullfrog              | Bus        | 2
CITY     | City                            | Bus        | 2
STBA     | Stagecoach - Airport Shuttle    | Bus        | 1
```

**Q2 — busiest stops by scheduled departures:**

```
stop_id        | stop_name                  | scheduled_stops
BEATTY_AIRPORT | Nye County Airport (Demo)  | 7
AMV            | Amargosa Valley (Demo)     | 4
BULLFROG       | Bullfrog (Demo)            | 4
```

**Q4 — service span per route (correct ordering from zero-padded times):**

```
route_id | route_long_name              | first_departure | last_arrival
CITY     | City                         | 06:00:00        | 06:56:00
AAMV     | Airport - Amargosa Valley    | 08:00:00        | 16:00:00
```

**Q5 — average headway per route (minutes):**

```
route_id | route_long_name              | avg_headway_minutes
CITY     | City                         | 22.0
STBA     | Stagecoach - Airport Shuttle | 30.0
```

See `queries.sql` for all five queries (Q3 = distinct stops served per route).
