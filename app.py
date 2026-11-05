from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, render_template, request

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

MIN_PREDICTION_SAMPLE = 30
PRIOR_WEIGHT = 20


class DatabaseConfigurationError(RuntimeError):
    pass


def connect_db():
    required = ("MYSQL_HOST", "MYSQL_DATABASE")
    missing = [key for key in required if not os.getenv(key)]
    user = os.getenv("APP_MYSQL_USER")
    password = os.getenv("APP_MYSQL_PASSWORD")
    if not user:
        missing.append("APP_MYSQL_USER")
    if not password:
        missing.append("APP_MYSQL_PASSWORD")
    if missing:
        raise DatabaseConfigurationError(
            "Variables absentes du fichier .env : " + ", ".join(missing)
        )

    config: dict[str, Any] = {
        "host": os.environ["MYSQL_HOST"],
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": user,
        "password": password,
        "database": os.environ["MYSQL_DATABASE"],
        "charset": "utf8mb4",
        "connection_timeout": 10,
    }

    if os.getenv("MYSQL_SSL_DISABLED", "").lower() == "true":
        config["ssl_disabled"] = True
    else:
        ca_path = os.getenv("MYSQL_SSL_CA")
        if not ca_path:
            raise DatabaseConfigurationError(
                "MYSQL_SSL_CA doit pointer vers le certificat CA TLS du fournisseur."
            )
        if not Path(ca_path).is_file():
            raise DatabaseConfigurationError(
                f"Certificat CA MySQL introuvable : {ca_path}"
            )
        config.update(
            ssl_ca=ca_path,
            ssl_verify_cert=True,
            ssl_verify_identity=True,
        )

    return mysql.connector.connect(**config)


def fetch_all(conn, sql: str, params: tuple = ()) -> list[dict]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        cursor.close()


def fetch_one(conn, sql: str, params: tuple = ()) -> dict:
    rows = fetch_all(conn, sql, params)
    if not rows:
        raise RuntimeError("La requête d'indicateur n'a retourné aucun résultat.")
    return rows[0]


def dashboard_data(conn) -> dict:
    summary = fetch_one(
        conn,
        """
        SELECT COUNT(*) AS total_flights,
               SUM(dep_time IS NOT NULL) AS operated_flights,
               SUM(dep_time IS NULL) AS cancelled_flights,
               ROUND(AVG(dep_delay), 1) AS average_departure_delay,
               ROUND(100 * AVG(dep_time IS NULL), 2) AS cancellation_rate,
               ROUND(100 * AVG(dep_delay >= 15), 2) AS late_departure_rate
        FROM flights
        """,
    )
    monthly = fetch_all(
        conn,
        """
        SELECT month,
               SUM(dep_time IS NOT NULL) AS flight_count,
               ROUND(AVG(dep_delay), 1) AS average_delay,
               ROUND(100 * AVG(dep_time IS NULL), 2) AS cancellation_rate,
               ROUND(100 * AVG(dep_delay >= 15), 2) AS late_rate
        FROM flights
        GROUP BY month
        ORDER BY month
        """,
    )
    airlines = fetch_all(
        conn,
        """
        SELECT a.carrier, a.name,
               COUNT(*) AS flight_count,
               ROUND(AVG(f.dep_delay), 1) AS average_delay,
               ROUND(100 * AVG(f.dep_time IS NULL), 2) AS cancellation_rate,
               ROUND(100 * AVG(f.dep_delay >= 15), 2) AS late_rate
        FROM flights f
        JOIN airlines a ON a.carrier = f.carrier
        GROUP BY a.carrier, a.name
        HAVING COUNT(*) >= 100
        ORDER BY average_delay DESC
        LIMIT 10
        """,
    )
    destinations = fetch_all(
        conn,
        """
        SELECT f.dest, a.name,
               COUNT(*) AS flight_count,
               ROUND(AVG(f.dep_delay), 1) AS average_delay,
               ROUND(100 * AVG(f.dep_delay >= 15), 2) AS late_rate
        FROM flights f
        JOIN airports a ON a.faa = f.dest
        GROUP BY f.dest, a.name
        HAVING COUNT(*) >= 100
        ORDER BY late_rate DESC, flight_count DESC
        LIMIT 10
        """,
    )
    weather_impact = fetch_all(
        conn,
        """
        SELECT weather_group,
               COUNT(*) AS flight_count,
               ROUND(AVG(dep_delay), 1) AS average_delay,
               ROUND(100 * AVG(dep_time IS NULL), 2) AS cancellation_rate,
               ROUND(100 * AVG(dep_delay >= 15), 2) AS late_rate
        FROM (
            SELECT f.dep_time, f.dep_delay,
                   CASE
                       WHEN w.precip IS NULL THEN 'Indisponible'
                       WHEN w.precip = 0 THEN 'Aucune'
                       WHEN w.precip <= 0.1 THEN 'Faible'
                       ELSE 'Forte'
                   END AS weather_group
            FROM flights f
            LEFT JOIN weather w
                ON w.origin = f.origin
               AND w.time_hour = f.time_hour
        ) AS historical_weather
        GROUP BY weather_group
        ORDER BY FIELD(weather_group, 'Aucune', 'Faible', 'Forte', 'Indisponible')
        """,
    )
    origins = fetch_all(
        conn,
        """
        SELECT f.origin, a.name, COUNT(*) AS flight_count,
               ROUND(AVG(f.dep_delay), 1) AS average_delay
        FROM flights f
        JOIN airports a ON a.faa = f.origin
        WHERE f.dep_time IS NOT NULL
        GROUP BY f.origin, a.name
        ORDER BY flight_count DESC
        """,
    )
    origin_options = fetch_all(
        conn,
        """
        SELECT DISTINCT a.faa, a.name
        FROM flights f
        JOIN airports a ON a.faa = f.origin
        ORDER BY a.faa
        """,
    )
    airport_options = fetch_all(
        conn,
        """
        SELECT faa, name
        FROM airports
        WHERE faa IN (SELECT origin FROM flights)
           OR faa IN (SELECT dest FROM flights)
        ORDER BY faa
        """,
    )
    carrier_options = fetch_all(
        conn,
        """
        SELECT DISTINCT a.carrier, a.name
        FROM airlines a
        JOIN flights f ON f.carrier = a.carrier
        ORDER BY a.name
        """,
    )

    max_flights = max((row["flight_count"] for row in origins), default=1)
    for row in origins:
        row["bar_width"] = round(100 * row["flight_count"] / max_flights)

    max_monthly = max((row["flight_count"] for row in monthly), default=1)
    for row in monthly:
        row["bar_width"] = round(100 * row["flight_count"] / max_monthly)

    return {
        "summary": summary,
        "monthly": monthly,
        "airlines": airlines,
        "destinations": destinations,
        "weather_impact": weather_impact,
        "origins": origins,
        "origin_options": origin_options,
        "airport_options": airport_options,
        "carrier_options": carrier_options,
    }


def historical_risk(
    conn,
    origin: str,
    destination: str | None,
    carrier: str | None,
    month: int,
    hour: int,
) -> dict:
    dimensions = [
        ("origin", origin, "aéroport de départ"),
        ("dest", destination, "trajet"),
        ("carrier", carrier, "compagnie"),
        ("month", month, "mois"),
        ("`hour`", hour, "heure programmée"),
    ]
    selected_filters = [(column, value, label) for column, value, label in dimensions if value is not None]

    origin_stats = fetch_one(
        conn,
        """
        SELECT COUNT(*) AS sample_size,
               SUM(dep_time IS NULL OR dep_delay >= 15) AS issue_count,
               AVG(dep_delay) AS average_delay
        FROM flights
        WHERE origin = %s
        """,
        (origin,),
    )
    if not origin_stats["sample_size"]:
        raise ValueError(f"Aucun vol historique trouvé pour l'origine {origin}.")
    prior_rate = origin_stats["issue_count"] / origin_stats["sample_size"]

    scopes = [
        selected_filters,
        [item for item in selected_filters if item[0] in ("origin", "dest", "carrier")],
        [item for item in selected_filters if item[0] in ("origin", "dest")],
        [item for item in selected_filters if item[0] in ("origin", "carrier")],
        [dimensions[0]],
    ]
    unique_scopes = []
    seen = set()
    for scope in scopes:
        key = tuple((column, value) for column, value, _ in scope)
        if key not in seen:
            seen.add(key)
            unique_scopes.append(scope)

    chosen = None
    chosen_scope = None
    for scope in unique_scopes:
        where = " AND ".join(f"{column} = %s" for column, _, _ in scope)
        params = tuple(value for _, value, _ in scope)
        stats = fetch_one(
            conn,
            f"""
            SELECT COUNT(*) AS sample_size,
                   SUM(dep_time IS NULL OR dep_delay >= 15) AS issue_count,
                   AVG(dep_delay) AS average_delay
            FROM flights
            WHERE {where}
            """,
            params,
        )
        chosen = stats
        chosen_scope = scope
        if stats["sample_size"] >= MIN_PREDICTION_SAMPLE:
            break

    if chosen is None or chosen_scope is None or not chosen["sample_size"]:
        raise ValueError("Pas assez d'historique pour produire une estimation.")

    sample_size = int(chosen["sample_size"])
    issue_count = int(chosen["issue_count"] or 0)
    rate = (issue_count + PRIOR_WEIGHT * prior_rate) / (
        sample_size + PRIOR_WEIGHT
    )
    confidence = (
        "élevé" if sample_size >= 1000 else "modéré" if sample_size >= 100 else "faible"
    )
    scope_label = ", ".join(label for _, _, label in chosen_scope)

    return {
        "risk_percent": round(100 * rate, 1),
        "sample_size": sample_size,
        "issue_count": issue_count,
        "average_delay": (
            round(float(chosen["average_delay"]), 1)
            if chosen["average_delay"] is not None
            else None
        ),
        "confidence": confidence,
        "scope": scope_label,
        "prior_percent": round(100 * prior_rate, 1),
    }


@app.get("/")
def index():
    try:
        conn = connect_db()
        try:
            data = dashboard_data(conn)
            prediction = None
            error = None
            form = {
                "origin": request.args.get("origin", "JFK").upper(),
                "destination": request.args.get("destination", "SEA").upper(),
                "carrier": request.args.get("carrier", ""),
                "month": request.args.get("month", "7"),
                "hour": request.args.get("hour", "12"),
            }
            if request.args.get("predict"):
                valid_origins = {row["faa"] for row in data["origin_options"]}
                valid_destinations = {
                    row["faa"] for row in data["airport_options"]
                } | {""}
                valid_carriers = {row["carrier"] for row in data["carrier_options"]}
                if form["origin"] not in valid_origins:
                    error = "Sélectionnez un aéroport de départ valide."
                elif form["destination"] not in valid_destinations:
                    error = "Sélectionnez une destination valide."
                elif form["carrier"] and form["carrier"] not in valid_carriers:
                    error = "Sélectionnez une compagnie valide."
                else:
                    try:
                        month = int(form["month"])
                        hour = int(form["hour"])
                        if not 1 <= month <= 12 or not 0 <= hour <= 23:
                            raise ValueError
                    except ValueError:
                        error = "Le mois doit être entre 1 et 12 et l'heure entre 0 et 23."
                    else:
                        prediction = historical_risk(
                            conn,
                            origin=form["origin"],
                            destination=form["destination"] or None,
                            carrier=form["carrier"] or None,
                            month=month,
                            hour=hour,
                        )
            return render_template(
                "dashboard.html",
                **data,
                prediction=prediction,
                prediction_error=error,
                form=form,
            )
        finally:
            conn.close()
    except (DatabaseConfigurationError, mysql.connector.Error) as exc:
        app.logger.exception("Dashboard could not query MySQL")
        return (
            render_template(
                "database_error.html",
                message=str(exc),
                ssl_disabled=os.getenv("MYSQL_SSL_DISABLED", "").lower() == "true",
            ),
            503,
        )


@app.get("/health")
def health():
    try:
        conn = connect_db()
        try:
            fetch_one(conn, "SELECT 1 AS database_ok")
        finally:
            conn.close()
    except (DatabaseConfigurationError, mysql.connector.Error) as exc:
        app.logger.exception("Database health check failed")
        return {"status": "unavailable", "detail": str(exc)}, 503
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
