-- ============================================================================
-- queries.sql  —  Sample analytical queries for the normalized GTFS database
-- Run against gtfs.db (built by etl.py), e.g.:
--     sqlite3 gtfs.db < queries.sql
-- Each query is independent and demonstrates a different join path.
-- ============================================================================


-- Q1. Trips per route, with the human-readable route type from the lookup table.
--     Demonstrates the route_type normalization (code -> description).
SELECT  r.route_id,
        r.route_long_name,
        rt.description           AS route_type,
        COUNT(t.trip_id)         AS num_trips
FROM        routes      r
JOIN        route_type  rt ON rt.route_type_id = r.route_type
LEFT JOIN   trips       t  ON t.route_id       = r.route_id
GROUP BY    r.route_id, r.route_long_name, rt.description
ORDER BY    num_trips DESC;


-- Q2. Busiest stops by number of scheduled departures (stop_times rows).
SELECT  s.stop_id,
        s.stop_name,
        COUNT(*)                 AS scheduled_stops
FROM        stop_times  st
JOIN        stops       s  ON s.stop_id = st.stop_id
GROUP BY    s.stop_id, s.stop_name
ORDER BY    scheduled_stops DESC
LIMIT 5;


-- Q3. Number of distinct stops served by each route (network coverage).
SELECT  r.route_id,
        r.route_long_name,
        COUNT(DISTINCT st.stop_id) AS stops_served
FROM        routes      r
JOIN        trips       t  ON t.route_id = r.route_id
JOIN        stop_times  st ON st.trip_id = t.trip_id
GROUP BY    r.route_id, r.route_long_name
ORDER BY    stops_served DESC;


-- Q4. Daily service span per route (first departure -> last arrival).
--     Relies on zero-padded 'HH:MM:SS' times so text MIN/MAX sort correctly.
SELECT  r.route_id,
        r.route_long_name,
        MIN(st.departure_time)   AS first_departure,
        MAX(st.arrival_time)     AS last_arrival
FROM        routes      r
JOIN        trips       t  ON t.route_id = r.route_id
JOIN        stop_times  st ON st.trip_id = t.trip_id
GROUP BY    r.route_id, r.route_long_name
ORDER BY    first_departure;


-- Q5. Average service frequency (headway) per route, from the frequencies table.
SELECT  r.route_id,
        r.route_long_name,
        ROUND(AVG(f.headway_secs) / 60.0, 1) AS avg_headway_minutes
FROM        frequencies f
JOIN        trips       t  ON t.trip_id  = f.trip_id
JOIN        routes      r  ON r.route_id = t.route_id
GROUP BY    r.route_id, r.route_long_name
ORDER BY    avg_headway_minutes;
