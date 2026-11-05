-- Row counts
SELECT 'airlines' AS table_name, COUNT(*) AS row_count FROM airlines
UNION ALL SELECT 'airports', COUNT(*) FROM airports
UNION ALL SELECT 'planes', COUNT(*) FROM planes
UNION ALL SELECT 'weather', COUNT(*) FROM weather
UNION ALL SELECT 'flights', COUNT(*) FROM flights;

SELECT
    SUM(tailnum IS NULL) AS flights_without_tailnum,
    SUM(tailnum IS NOT NULL) AS flights_with_tailnum
FROM flights;

-- flight alone is not a primary key; the composite flight key is unique.
SELECT
    COUNT(*) AS flight_rows,
    COUNT(DISTINCT flight) AS distinct_flight_numbers,
    (SELECT COUNT(*) FROM (
        SELECT year, month, day, `hour`, carrier, flight
        FROM flights
        GROUP BY year, month, day, `hour`, carrier, flight
        HAVING COUNT(*) > 1
    ) AS duplicate_flight_keys) AS duplicate_composite_keys
FROM flights;

-- Format checks. These should all return zero.
SELECT COUNT(*) AS invalid_airport_codes
FROM airports WHERE NOT REGEXP_LIKE(faa, '^[A-Z0-9]{3}$', 'c');

SELECT COUNT(*) AS invalid_carrier_codes
FROM airlines WHERE NOT REGEXP_LIKE(carrier, '^[A-Z0-9]{2}$', 'c');

SELECT COUNT(*) AS invalid_flight_airport_codes
FROM flights
WHERE NOT REGEXP_LIKE(origin, '^[A-Z0-9]{3}$', 'c')
   OR NOT REGEXP_LIKE(dest, '^[A-Z0-9]{3}$', 'c');

SELECT COUNT(*) AS invalid_weather_airport_codes
FROM weather WHERE NOT REGEXP_LIKE(origin, '^[A-Z0-9]{3}$', 'c');

SELECT COUNT(*) AS invalid_plane_tailnums
FROM planes WHERE NOT REGEXP_LIKE(tailnum, '^N[A-Z0-9]{1,5}$', 'c');

-- The suggested weather key collides at the repeated local 01:00 during the
-- daylight-saving transition. time_hour distinguishes the two UTC instants.
SELECT COUNT(*) AS duplicate_groups_in_suggested_weather_key
FROM (
    SELECT year, month, day, `hour`, origin
    FROM weather
    GROUP BY year, month, day, `hour`, origin
    HAVING COUNT(*) > 1
) AS weather_key_collisions;

SELECT COUNT(*) AS duplicate_groups_in_weather_primary_key
FROM (
    SELECT year, month, day, `hour`, origin, time_hour
    FROM weather
    GROUP BY year, month, day, `hour`, origin, time_hour
    HAVING COUNT(*) > 1
) AS duplicate_weather_keys;

SELECT 'flight origin' AS relation_name, COUNT(*) AS unmatched_rows
FROM flights f LEFT JOIN airports a ON a.faa = f.origin
WHERE a.faa IS NULL
UNION ALL
SELECT 'flight destination', COUNT(*)
FROM flights f LEFT JOIN airports a ON a.faa = f.dest
WHERE a.faa IS NULL
UNION ALL
SELECT 'flight carrier', COUNT(*)
FROM flights f LEFT JOIN airlines a ON a.carrier = f.carrier
WHERE a.carrier IS NULL
UNION ALL
SELECT 'flight plane (non-null tailnum)', COUNT(*)
FROM flights f LEFT JOIN planes p ON p.tailnum = f.tailnum
WHERE f.tailnum IS NOT NULL AND p.tailnum IS NULL
UNION ALL
SELECT 'weather origin', COUNT(*)
FROM weather w LEFT JOIN airports a ON a.faa = w.origin
WHERE a.faa IS NULL;

-- Reference rows were added without inventing geographic/technical metadata.
SELECT faa, name, metadata_source
FROM airports
WHERE metadata_source = 'flight_reference'
ORDER BY faa;

SELECT tailnum, metadata_source
FROM planes
WHERE metadata_source = 'flight_reference'
ORDER BY tailnum;

-- Many-to-many carrier/airport relationship, observed through flights.
SELECT carrier, COUNT(DISTINCT dest) AS destination_airports
FROM flights
GROUP BY carrier
ORDER BY carrier;

SELECT dest AS airport, COUNT(DISTINCT carrier) AS serving_carriers
FROM flights
GROUP BY dest
ORDER BY dest;
