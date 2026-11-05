-- Requetes d'exploration pour nycflights13
-- Base attendue: airdata. Les codes horaires sont entre backticks car HOUR
-- est une fonction/reserve potentielle en SQL.

-- 1. Nombre d'aeroports
-- Nombre de lignes dans le referentiel, d'origines, de destinations et nombre
-- d'aeroports distincts vus en origine ou destination dans les vols.
SELECT
    (SELECT COUNT(*) FROM airports) AS airports_in_reference,
    (SELECT COUNT(DISTINCT origin) FROM flights) AS departure_airports,
    (SELECT COUNT(DISTINCT dest) FROM flights) AS destination_airports,
    (
        SELECT COUNT(DISTINCT airport_code)
        FROM (
            SELECT origin AS airport_code FROM flights
            UNION
            SELECT dest AS airport_code FROM flights
        ) AS used_airports
    ) AS distinct_airports_used;

-- Aeroports ne passant pas a l'heure d'ete. La valeur 'N' indique qu'il n'y a
-- pas de changement saisonnier; la requete suivante donne aussi la distribution.
SELECT COUNT(*) AS airports_without_daylight_saving
FROM airports
WHERE UPPER(dst) = 'N';

SELECT dst, COUNT(*) AS airport_count
FROM airports
GROUP BY dst
ORDER BY dst;

-- Nombre de fuseaux horaires distincts, y compris les valeurs NULL/N eventuelles.
SELECT
    COUNT(DISTINCT tzone) AS distinct_named_time_zones,
    SUM(tzone = 'N') AS airports_with_tzone_N,
    SUM(tzone IS NULL) AS airports_with_unknown_tzone
FROM airports;

-- Compagnies, avions et vols annules. Un vol annule n'a pas d'heure de depart.
SELECT
    (SELECT COUNT(*) FROM airlines) AS airline_count,
    (SELECT COUNT(*) FROM planes) AS plane_records,
    (SELECT COUNT(*) FROM flights) AS flight_count,
    (SELECT COUNT(*) FROM flights WHERE dep_time IS NULL) AS cancelled_flights;

SELECT a.carrier, a.name, COUNT(*) AS cancelled_flights
FROM flights f
JOIN airlines a ON a.carrier = f.carrier
WHERE f.dep_time IS NULL
GROUP BY a.carrier, a.name
ORDER BY cancelled_flights DESC, a.name;

-- 2. Aeroport de depart le plus utilise
SELECT a.faa, a.name, COUNT(*) AS departing_flights
FROM flights f
JOIN airports a ON a.faa = f.origin
WHERE f.dep_time IS NOT NULL
GROUP BY a.faa, a.name
ORDER BY departing_flights DESC, a.name
LIMIT 1;

-- Dix destinations les plus prises: nombre de vols et part du total des vols.
SELECT a.faa, a.name, COUNT(*) AS flight_count,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM flights), 2) AS percent_of_all_flights
FROM flights f
JOIN airports a ON a.faa = f.dest
GROUP BY a.faa, a.name
ORDER BY flight_count DESC, a.name
LIMIT 10;

-- Dix destinations les moins prises (parmi celles ayant au moins un vol).
SELECT a.faa, a.name, COUNT(*) AS flight_count,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM flights), 2) AS percent_of_all_flights
FROM flights f
JOIN airports a ON a.faa = f.dest
GROUP BY a.faa, a.name
ORDER BY flight_count ASC, a.name
LIMIT 10;

-- Dix avions avec le plus de departs (les vols sans tailnum sont exclus).
SELECT f.tailnum, p.manufacturer, p.model, COUNT(*) AS departure_count
FROM flights f
LEFT JOIN planes p ON p.tailnum = f.tailnum
WHERE f.tailnum IS NOT NULL AND f.dep_time IS NOT NULL
GROUP BY f.tailnum, p.manufacturer, p.model
ORDER BY departure_count DESC, f.tailnum
LIMIT 10;

-- Dix avions avec le moins de departs parmi ceux ayant vole au moins une fois.
SELECT f.tailnum, p.manufacturer, p.model, COUNT(*) AS departure_count
FROM flights f
LEFT JOIN planes p ON p.tailnum = f.tailnum
WHERE f.tailnum IS NOT NULL AND f.dep_time IS NOT NULL
GROUP BY f.tailnum, p.manufacturer, p.model
ORDER BY departure_count ASC, f.tailnum
LIMIT 10;

-- 3. Resultat pret a tracer: nombre de destinations desservies par compagnie.
SELECT a.carrier, a.name, COUNT(DISTINCT f.dest) AS destination_count
FROM airlines a
LEFT JOIN flights f ON f.carrier = a.carrier
GROUP BY a.carrier, a.name
ORDER BY destination_count DESC, a.name;

-- Resultat pret a tracer: nombre de destinations par compagnie et aeroport d'origine.
SELECT a.carrier, a.name AS airline_name,
       f.origin AS origin_code, o.name AS origin_name,
       COUNT(DISTINCT f.dest) AS destination_count
FROM flights f
JOIN airlines a ON a.carrier = f.carrier
JOIN airports o ON o.faa = f.origin
GROUP BY a.carrier, a.name, f.origin, o.name
ORDER BY a.name, o.name;

-- Resultat pret a tracer: vols par compagnie, origine et destination.
SELECT a.carrier, a.name AS airline_name,
       f.origin AS origin_code, o.name AS origin_name,
       f.dest AS destination_code, d.name AS destination_name,
       COUNT(*) AS flight_count
FROM flights f
JOIN airlines a ON a.carrier = f.carrier
JOIN airports o ON o.faa = f.origin
JOIN airports d ON d.faa = f.dest
GROUP BY a.carrier, a.name, f.origin, o.name, f.dest, d.name
ORDER BY a.name, o.name, d.name;

-- 4. Tous les vols a destination de Houston (IAH ou HOU).
SELECT f.*, d.name AS destination_name, a.name AS airline_name
FROM flights f
JOIN airports d ON d.faa = f.dest
JOIN airlines a ON a.carrier = f.carrier
WHERE f.dest IN ('IAH', 'HOU')
  AND f.arr_time IS NOT NULL
ORDER BY f.year, f.month, f.day, f.dep_time;

-- Vols NYC -> Seattle (SEA), compagnies et avions uniques.
SELECT
    COUNT(*) AS flights_to_seattle,
    COUNT(DISTINCT carrier) AS airlines_to_seattle,
    COUNT(DISTINCT tailnum) AS unique_planes_to_seattle
FROM flights
WHERE dest = 'SEA' AND dep_time IS NOT NULL;

-- Details: les vols, compagnies et avions vers Seattle.
SELECT f.*, a.name AS airline_name, o.name AS origin_name, d.name AS destination_name
FROM flights f
JOIN airlines a ON a.carrier = f.carrier
JOIN airports o ON o.faa = f.origin
JOIN airports d ON d.faa = f.dest
WHERE f.dest = 'SEA' AND f.dep_time IS NOT NULL
ORDER BY f.year, f.month, f.day, f.dep_time;

-- 5. Nombre de vols par destination.
SELECT d.faa AS destination_code, d.name AS destination_name,
       COUNT(*) AS flight_count
FROM flights f
JOIN airports d ON d.faa = f.dest
GROUP BY d.faa, d.name
ORDER BY flight_count DESC, d.name;

-- Vols tries alphabetiquement par destination, origine et compagnie;
-- les jointures donnent les noms explicites des aeroports.
SELECT f.*, d.name AS destination_name, o.name AS origin_name,
       a.name AS airline_name
FROM flights f
JOIN airports d ON d.faa = f.dest
JOIN airports o ON o.faa = f.origin
JOIN airlines a ON a.carrier = f.carrier
ORDER BY d.name ASC, o.name ASC, a.name ASC,
         f.year, f.month, f.day, f.dep_time;

-- 6. Compagnies qui ne desservent pas tous les aeroports d'origine (JFK, LGA, EWR).
SELECT a.carrier, a.name
FROM airlines a
WHERE EXISTS (SELECT 1 FROM flights)
  AND (
      SELECT COUNT(DISTINCT f.origin)
      FROM flights f
      WHERE f.carrier = a.carrier
  ) < (SELECT COUNT(DISTINCT origin) FROM flights)
ORDER BY a.name;

-- Compagnies desservant tous les codes de destination observes dans le jeu.
SELECT a.carrier, a.name
FROM airlines a
WHERE EXISTS (SELECT 1 FROM flights)
  AND NOT EXISTS (
      SELECT 1
      FROM (SELECT DISTINCT dest FROM flights) AS all_destinations
      WHERE NOT EXISTS (
          SELECT 1
          FROM flights f
          WHERE f.carrier = a.carrier
            AND f.dest = all_destinations.dest
      )
  )
ORDER BY a.name;

-- Pour chaque compagnie: liste des aeroports d'origine et destinations observes.
-- Les sous-requetes evitent le produit cartesien entre origines et destinations.
SELECT a.carrier, a.name AS airline_name,
       (
           SELECT GROUP_CONCAT(
               DISTINCT CONCAT(o.faa, ' - ', o.name)
               ORDER BY o.name SEPARATOR '; '
           )
           FROM flights fo
           JOIN airports o ON o.faa = fo.origin
           WHERE fo.carrier = a.carrier
       ) AS origins,
       (
           SELECT GROUP_CONCAT(
               DISTINCT CONCAT(d.faa, ' - ', d.name)
               ORDER BY d.name SEPARATOR '; '
           )
           FROM flights fd
           JOIN airports d ON d.faa = fd.dest
           WHERE fd.carrier = a.carrier
       ) AS destinations
FROM airlines a
ORDER BY a.name;

-- 7. Destinations desservies par une seule compagnie (exclusives).
SELECT d.faa AS destination_code, d.name AS destination_name,
       a.carrier, a.name AS airline_name,
       COUNT(*) AS flight_count
FROM flights f
JOIN airports d ON d.faa = f.dest
JOIN airlines a ON a.carrier = f.carrier
WHERE f.dest IN (
    SELECT exclusive_dest.dest
    FROM (
        SELECT dest
        FROM flights
        GROUP BY dest
        HAVING COUNT(DISTINCT carrier) = 1
    ) AS exclusive_dest
)
GROUP BY d.faa, d.name, a.carrier, a.name
ORDER BY d.name, a.name;

-- 8. Vols exploites par United, American ou Delta (codes IATA du jeu).
SELECT f.*, a.name AS airline_name,
       o.name AS origin_name, d.name AS destination_name
FROM flights f
JOIN airlines a ON a.carrier = f.carrier
JOIN airports o ON o.faa = f.origin
JOIN airports d ON d.faa = f.dest
WHERE f.carrier IN ('UA', 'AA', 'DL')
ORDER BY a.name, f.year, f.month, f.day, f.dep_time;
