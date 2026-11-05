from __future__ import annotations

import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

CHECKS = {
    "vols": "SELECT COUNT(*) FROM flights",
    "numéros de vol distincts": (
        "SELECT COUNT(DISTINCT flight) FROM flights"
    ),
    "clés composites dupliquées": """
        SELECT COUNT(*) FROM (
            SELECT year, month, day, `hour`, carrier, flight
            FROM flights
            GROUP BY year, month, day, `hour`, carrier, flight
            HAVING COUNT(*) > 1
        ) duplicates
    """,
    "collisions dans la clé météo proposée": """
        SELECT COUNT(*) FROM (
            SELECT year, month, day, `hour`, origin
            FROM weather
            GROUP BY year, month, day, `hour`, origin
            HAVING COUNT(*) > 1
        ) collisions
    """,
    "clés primaires météo dupliquées": """
        SELECT COUNT(*) FROM (
            SELECT year, month, day, `hour`, origin, time_hour
            FROM weather
            GROUP BY year, month, day, `hour`, origin, time_hour
            HAVING COUNT(*) > 1
        ) duplicates
    """,
    "codes aéroports invalides": """
        SELECT COUNT(*) FROM airports
        WHERE NOT REGEXP_LIKE(faa, '^[A-Z0-9]{3}$', 'c')
    """,
    "codes compagnies invalides": """
        SELECT COUNT(*) FROM airlines
        WHERE NOT REGEXP_LIKE(carrier, '^[A-Z0-9]{2}$', 'c')
    """,
    "codes compagnies invalides dans flights": """
        SELECT COUNT(*) FROM flights
        WHERE NOT REGEXP_LIKE(carrier, '^[A-Z0-9]{2}$', 'c')
    """,
    "immatriculations invalides": """
        SELECT COUNT(*) FROM planes
        WHERE NOT REGEXP_LIKE(tailnum, '^N[A-Z0-9]{1,5}$', 'c')
    """,
    "codes origin/dest invalides dans flights": """
        SELECT COUNT(*) FROM flights
        WHERE NOT REGEXP_LIKE(origin, '^[A-Z0-9]{3}$', 'c')
           OR NOT REGEXP_LIKE(dest, '^[A-Z0-9]{3}$', 'c')
    """,
    "codes origin invalides dans weather": """
        SELECT COUNT(*) FROM weather
        WHERE NOT REGEXP_LIKE(origin, '^[A-Z0-9]{3}$', 'c')
    """,
    "FK origin/destination invalides": """
        SELECT (
            SELECT COUNT(*) FROM flights f
            LEFT JOIN airports a ON a.faa = f.origin
            WHERE a.faa IS NULL
        ) + (
            SELECT COUNT(*) FROM flights f
            LEFT JOIN airports a ON a.faa = f.dest
            WHERE a.faa IS NULL
        )
    """,
    "FK compagnie invalides": """
        SELECT COUNT(*) FROM flights f
        LEFT JOIN airlines a ON a.carrier = f.carrier
        WHERE a.carrier IS NULL
    """,
    "FK avion invalides": """
        SELECT COUNT(*) FROM flights f
        LEFT JOIN planes p ON p.tailnum = f.tailnum
        WHERE f.tailnum IS NOT NULL AND p.tailnum IS NULL
    """,
    "FK météo/aéroport invalides": """
        SELECT COUNT(*) FROM weather w
        LEFT JOIN airports a ON a.faa = w.origin
        WHERE a.faa IS NULL
    """,
}


def main() -> None:
    load_dotenv(ROOT / ".env")
    required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE", "MYSQL_SSL_CA")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            "Variables MySQL absentes du fichier .env: " + ", ".join(missing)
        )
    ssl_ca = Path(os.environ["MYSQL_SSL_CA"])
    if not ssl_ca.is_file():
        raise FileNotFoundError(f"Certificat CA MySQL introuvable: {ssl_ca}")

    config = {
        "host": os.environ["MYSQL_HOST"],
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
        "database": os.environ["MYSQL_DATABASE"],
        "charset": "utf8mb4",
        "ssl_ca": str(ssl_ca),
        "ssl_verify_cert": True,
        "ssl_verify_identity": True,
    }
    with mysql.connector.connect(**config) as conn:
        with conn.cursor() as cur:
            results = {}
            for name, query in CHECKS.items():
                cur.execute(query)
                results[name] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM flights WHERE tailnum IS NULL")
            missing_tailnums = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM planes "
                "WHERE metadata_source = 'flight_reference'"
            )
            plane_stubs = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM airports "
                "WHERE metadata_source = 'flight_reference'"
            )
            airport_stubs = cur.fetchone()[0]

    for name, value in results.items():
        print(f"{name}: {value}")
    print(f"Vols sans tailnum dans la source: {missing_tailnums}")
    print(f"Fiches avions de référence sans métadonnées: {plane_stubs}")
    print(f"Aéroports de référence sans métadonnées géographiques: {airport_stubs}")

    failures = [
        f"{name}={value}"
        for name, value in results.items()
        if (name == "vols" and value != 336_776)
        or (
            name == "numéros de vol distincts"
            and value >= results["vols"]
        )
        or (
            name == "collisions dans la clé météo proposée"
            and value != 3
        )
        or (
            name not in (
                "vols",
                "numéros de vol distincts",
                "collisions dans la clé météo proposée",
            )
            and value != 0
        )
    ]
    if failures:
        raise SystemExit("ÉCHEC des vérifications: " + "; ".join(failures))
    print("VÉRIFICATION OK")


if __name__ == "__main__":
    main()
