from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.request import urlretrieve

import pandas as pd
import mysql.connector
import pyreadr
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / ".data"
SOURCE_COMMIT = "df98ef215aa8216fe0838a0b8ac5bada646d814c"
DATASETS = ("airlines", "airports", "planes", "weather", "flights")
AIRPORT_REFERENCES = {
    "BQN": "Rafael Hernandez Airport",
    "PSE": "Mercedita Airport",
    "SJU": "San Juan Airport",
    "STT": "Cyril E. King Airport",
}

TABLE_COLUMNS = {
    "airlines": ("carrier", "name"),
    "airports": ("faa", "name", "lat", "lon", "alt", "tz", "dst", "tzone"),
    "planes": (
        "tailnum", "year", "type", "manufacturer", "model",
        "engines", "seats", "speed", "engine",
    ),
    "weather": (
        "origin", "year", "month", "day", "hour", "temp", "dewp",
        "humid", "wind_dir", "wind_speed", "wind_gust", "precip",
        "pressure", "visib", "time_hour",
    ),
    "flights": (
        "year", "month", "day", "dep_time", "sched_dep_time", "dep_delay",
        "arr_time", "sched_arr_time", "arr_delay", "carrier", "flight",
        "tailnum", "origin", "dest", "air_time", "distance", "hour",
        "minute", "time_hour",
    ),
}

INTEGER_COLUMNS = {
    "airports": ("alt", "tz"),
    "planes": ("year", "engines", "seats", "speed"),
    "weather": ("year", "month", "day", "hour"),
    "flights": (
        "year", "month", "day", "dep_time", "sched_dep_time", "arr_time",
        "sched_arr_time", "flight", "distance", "hour", "minute",
    ),
}

KEY_COLUMNS = {
    "airlines": ("carrier",),
    "airports": ("faa",),
    "planes": ("tailnum",),
    "weather": ("year", "month", "day", "hour", "origin", "time_hour"),
    "flights": ("year", "month", "day", "hour", "carrier", "flight"),
}

CODE_PATTERNS = {
    "airlines.carrier": re.compile(r"^[A-Z0-9]{2}$"),
    "airports.faa": re.compile(r"^[A-Z0-9]{3}$"),
    "planes.tailnum": re.compile(r"^[A-Z0-9]{1,6}$"),
    "weather.origin": re.compile(r"^[A-Z0-9]{3}$"),
    "flights.origin": re.compile(r"^[A-Z0-9]{3}$"),
    "flights.dest": re.compile(r"^[A-Z0-9]{3}$"),
    "flights.carrier": re.compile(r"^[A-Z0-9]{2}$"),
}


def load_source_data() -> dict[str, pd.DataFrame]:
    DATA_DIR.mkdir(exist_ok=True)
    frames = {}
    for name in DATASETS:
        path = DATA_DIR / f"{name}.rda"
        if not path.exists():
            url = (
                "https://raw.githubusercontent.com/tidyverse/nycflights13/"
                f"{SOURCE_COMMIT}/data/{name}.rda"
            )
            print(f"Téléchargement de {name}...")
            urlretrieve(url, path)
        objects = pyreadr.read_r(str(path))
        if name not in objects:
            raise ValueError(f"Objet {name!r} absent de {path.name}.")
        frames[name] = objects[name]
    return frames


def validate_source(frames: dict[str, pd.DataFrame]) -> None:
    for table, keys in KEY_COLUMNS.items():
        frame = frames[table]
        missing = frame[list(keys)].isna().any(axis=1).sum()
        duplicates = frame.duplicated(list(keys)).sum()
        if missing or duplicates:
            raise ValueError(
                f"{table}: {missing} clés avec NULL, {duplicates} clés dupliquées."
            )

    suggested_weather_key = ("year", "month", "day", "hour", "origin")
    weather_collisions = frames["weather"].duplicated(
        list(suggested_weather_key)
    ).sum()
    collision_groups = (
        frames["weather"]
        .groupby(list(suggested_weather_key), dropna=False)
        .size()
        .gt(1)
        .sum()
    )
    print(
        "Clé météo proposée (sans time_hour): "
        f"{collision_groups} groupes en collision ({weather_collisions} lignes répétées); "
        "time_hour est ajouté pour distinguer l'heure répétée du changement d'heure."
    )

    for field, pattern in CODE_PATTERNS.items():
        table, column = field.split(".")
        values = frames[table][column].dropna().astype(str)
        invalid = values[~values.str.fullmatch(pattern)]
        if not invalid.empty:
            examples = invalid.drop_duplicates().head(5).tolist()
            raise ValueError(f"{field}: codes hors nomenclature, exemples: {examples}")

    airline_codes = set(frames["airlines"]["carrier"])
    airport_codes = set(frames["airports"]["faa"])
    plane_codes = set(frames["planes"]["tailnum"].dropna())

    missing_carriers = set(frames["flights"]["carrier"]) - airline_codes
    missing_airports = (
        set(frames["flights"]["origin"])
        | set(frames["flights"]["dest"])
        | set(frames["weather"]["origin"])
    ) - airport_codes
    unexpected_airports = missing_airports - AIRPORT_REFERENCES.keys()
    if missing_carriers:
        raise ValueError(f"Compagnies absentes de airlines: {sorted(missing_carriers)}")
    if unexpected_airports:
        raise ValueError(
            "Aéroports absents de airports sans métadonnées documentées: "
            f"{sorted(unexpected_airports)}"
        )

    missing_planes = set(frames["flights"]["tailnum"].dropna()) - plane_codes
    print(
        "Contrôles source: "
        f"{len(missing_airports)} aéroports à compléter, "
        f"{len(missing_planes)} avions référencés sans fiche planes, "
        f"{frames['flights']['tailnum'].isna().sum()} vols sans tailnum."
    )
    non_us_registrations = sorted(
        tailnum
        for tailnum in set(frames["flights"]["tailnum"].dropna().astype(str))
        if not re.fullmatch(r"N[A-Z0-9]{1,5}", tailnum)
    )
    if non_us_registrations:
        print(
            "Immatriculations valides hors format US N: "
            f"{len(non_us_registrations)} ({', '.join(non_us_registrations[:10])})."
        )


def insert_frame(cur, table: str, frame: pd.DataFrame) -> None:
    columns = TABLE_COLUMNS[table]
    missing_columns = set(columns) - set(frame.columns)
    if missing_columns:
        raise ValueError(f"{table}: colonnes absentes: {sorted(missing_columns)}")

    ordered = frame.loc[:, columns].copy()
    for column in INTEGER_COLUMNS.get(table, ()):
        ordered[column] = pd.to_numeric(ordered[column], errors="raise").astype("Int64")
    if "time_hour" in columns:
        ordered["time_hour"] = pd.to_datetime(
            ordered["time_hour"], utc=True
        ).dt.strftime("%Y-%m-%d %H:%M:%S")
    column_sql = ", ".join(f"`{column}`" for column in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    statement = f"INSERT INTO `{table}` ({column_sql}) VALUES ({placeholders})"

    batch = []
    for row in ordered.itertuples(index=False, name=None):
        values = []
        for value in row:
            if pd.isna(value):
                values.append(None)
            elif hasattr(value, "item"):
                values.append(value.item())
            else:
                values.append(value)
        batch.append(tuple(values))
        if len(batch) == 2000:
            cur.executemany(statement, batch)
            batch.clear()
    if batch:
        cur.executemany(statement, batch)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Télécharge et importe les données publiques nycflights13 dans MySQL."
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="remplace les données déjà présentes dans les cinq tables.",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    required = ("MYSQL_HOST", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(
            "Variables MySQL absentes du fichier .env: " + ", ".join(missing)
        )

    frames = load_source_data()
    validate_source(frames)
    schema_sql = (ROOT / "sql" / "01_schema.sql").read_text(encoding="utf-8")
    config = {
        "host": os.environ["MYSQL_HOST"],
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
        "database": os.environ["MYSQL_DATABASE"],
        "charset": "utf8mb4",
    }
    if os.getenv("MYSQL_SSL_DISABLED", "").lower() == "true":
        config["ssl_disabled"] = True
    else:
        ssl_ca = os.getenv("MYSQL_SSL_CA")
        if not ssl_ca:
            raise RuntimeError("MYSQL_SSL_CA doit pointer vers le certificat CA TLS.")
        if not Path(ssl_ca).is_file():
            raise FileNotFoundError(f"Certificat CA MySQL introuvable: {ssl_ca}")
        config.update(
            ssl_ca=ssl_ca,
            ssl_verify_cert=True,
            ssl_verify_identity=True,
        )

    with mysql.connector.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW STATUS LIKE 'Ssl_cipher'")
            ssl_status = cur.fetchone()
            if (
                os.getenv("MYSQL_SSL_DISABLED", "").lower() != "true"
                and (not ssl_status or not ssl_status[1])
            ):
                raise RuntimeError("Connexion MySQL non chiffrée: chargement annulé.")

            for statement in schema_sql.split(";"):
                if statement.strip():
                    cur.execute(statement)

            cur.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.TABLE_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'planes'
                  AND CONSTRAINT_NAME = 'planes_tailnum_format'
                  AND CONSTRAINT_TYPE = 'CHECK'
                """
            )
            if cur.fetchone()[0]:
                cur.execute("ALTER TABLE planes DROP CHECK planes_tailnum_format")
            cur.execute(
                """
                ALTER TABLE planes
                ADD CONSTRAINT planes_tailnum_format
                CHECK (REGEXP_LIKE(tailnum, '^[A-Z0-9]{1,6}$', 'c'))
                """
            )
            cur.execute(
                """
                SELECT COUNT(*)
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'weather'
                  AND INDEX_NAME = 'weather_origin_time_idx'
                """
            )
            if not cur.fetchone()[0]:
                cur.execute(
                    "ALTER TABLE weather "
                    "ADD KEY weather_origin_time_idx (origin, time_hour)"
                )

            conn.start_transaction()
            counts = {}
            for table in DATASETS:
                cur.execute(f"SELECT COUNT(*) FROM `{table}`")
                counts[table] = cur.fetchone()[0]
            populated = {table: count for table, count in counts.items() if count}
            if populated and not args.replace:
                conn.rollback()
                raise RuntimeError(
                    "La base contient déjà des données: "
                    + ", ".join(f"{table}={count}" for table, count in populated.items())
                    + ". Relancez avec --replace pour les remplacer."
                )
            if args.replace:
                for table in ("flights", "weather", "planes", "airports", "airlines"):
                    cur.execute(f"DELETE FROM `{table}`")

            for table in ("airlines", "airports", "planes"):
                insert_frame(cur, table, frames[table])

            airport_codes = (
                set(frames["flights"]["origin"])
                | set(frames["flights"]["dest"])
                | set(frames["weather"]["origin"])
            )
            known_airports = set(frames["airports"]["faa"])
            airport_stubs = [
                (code, AIRPORT_REFERENCES[code], "flight_reference")
                for code in sorted(airport_codes - known_airports)
            ]
            cur.executemany(
                "INSERT INTO airports (faa, name, metadata_source) "
                "VALUES (%s, %s, %s)",
                airport_stubs,
            )

            known_planes = set(frames["planes"]["tailnum"].dropna())
            referenced_planes = set(frames["flights"]["tailnum"].dropna())
            plane_stubs = [
                (tailnum, "flight_reference")
                for tailnum in sorted(referenced_planes - known_planes)
            ]
            cur.executemany(
                "INSERT INTO planes (tailnum, metadata_source) "
                "VALUES (%s, %s)",
                plane_stubs,
            )

            insert_frame(cur, "weather", frames["weather"])
            insert_frame(cur, "flights", frames["flights"])
            cur.execute("SELECT COUNT(*) FROM flights")
            flight_count = cur.fetchone()[0]
        conn.commit()
    print(
        f"Chargement terminé: {flight_count:,} vols; "
        f"SSL actif: {os.getenv('MYSQL_SSL_DISABLED', '').lower() != 'true'}."
    )


if __name__ == "__main__":
    main()
