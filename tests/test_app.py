from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import app as dashboard


class FakeConnection:
    def close(self):
        pass


class FakeRiskCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params):
        self.conn.queries.append((sql, params))
        if params == ("JFK",):
            self.result = {
                "sample_size": 100,
                "issue_count": 20,
                "average_delay": 10.0,
            }
        elif len(params) == 5:
            self.result = {
                "sample_size": 12,
                "issue_count": 8,
                "average_delay": 18.0,
            }
        else:
            self.result = {
                "sample_size": 40,
                "issue_count": 14,
                "average_delay": 15.0,
            }

    def fetchall(self):
        return [self.result]

    def close(self):
        pass


class FakeRiskConnection:
    def __init__(self):
        self.queries = []

    def cursor(self, dictionary=False):
        return FakeRiskCursor(self)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        dashboard.app.config.update(TESTING=True)
        self.client = dashboard.app.test_client()

    @staticmethod
    def sample_data():
        return {
            "summary": {
                "total_flights": 100,
                "operated_flights": 90,
                "cancelled_flights": 10,
                "average_departure_delay": 12.5,
                "cancellation_rate": 10,
                "late_departure_rate": 20,
            },
            "monthly": [],
            "airlines": [],
            "destinations": [],
            "weather_impact": [],
            "origins": [],
            "origin_options": [{"faa": "JFK", "name": "John F Kennedy Intl"}],
            "airport_options": [
                {"faa": "JFK", "name": "John F Kennedy Intl"},
                {"faa": "SEA", "name": "Seattle Tacoma Intl"},
            ],
            "carrier_options": [{"carrier": "UA", "name": "United Air Lines"}],
        }

    @patch.object(dashboard, "dashboard_data")
    @patch.object(dashboard, "connect_db", return_value=FakeConnection())
    def test_dashboard_renders_historical_metrics(self, _connect, load_data):
        load_data.return_value = self.sample_data()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Performance op", response.data)
        self.assertIn(b"2013", response.data)

    @patch.object(dashboard, "historical_risk")
    @patch.object(dashboard, "dashboard_data")
    @patch.object(dashboard, "connect_db", return_value=FakeConnection())
    def test_scenario_form_displays_historical_risk(
        self, _connect, load_data, estimate
    ):
        load_data.return_value = self.sample_data()
        estimate.return_value = {
            "risk_percent": 27.4,
            "sample_size": 150,
            "issue_count": 40,
            "average_delay": 13.2,
            "confidence": "modéré",
            "scope": "aéroport de départ, trajet",
            "prior_percent": 22.0,
        }
        response = self.client.get(
            "/?predict=1&origin=JFK&destination=SEA&carrier=UA&month=7&hour=12"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"27.4", response.data)
        estimate.assert_called_once()

    @patch.object(dashboard, "dashboard_data")
    @patch.object(dashboard, "connect_db", return_value=FakeConnection())
    def test_invalid_airport_is_rejected(self, _connect, load_data):
        load_data.return_value = self.sample_data()
        response = self.client.get("/?predict=1&origin=BAD&month=7&hour=12")
        self.assertEqual(response.status_code, 200)
        self.assertIn("aéroport de départ valide".encode(), response.data)

    @patch.object(
        dashboard,
        "connect_db",
        side_effect=dashboard.DatabaseConfigurationError("MYSQL_HOST manquant"),
    )
    def test_database_configuration_error_is_visible(self, _connect):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"MYSQL_HOST manquant", response.data)

    def test_historical_risk_falls_back_to_larger_comparison_group(self):
        conn = FakeRiskConnection()
        result = dashboard.historical_risk(
            conn,
            origin="JFK",
            destination="SEA",
            carrier="UA",
            month=7,
            hour=12,
        )
        self.assertEqual(result["sample_size"], 40)
        self.assertEqual(result["risk_percent"], 30.0)
        self.assertEqual(result["confidence"], "faible")
        self.assertEqual(conn.queries[2][1], ("JFK", "SEA", "UA"))
        self.assertNotIn("JFK", conn.queries[2][0])

    @patch.dict(
        os.environ,
        {
            "MYSQL_HOST": "db.example",
            "MYSQL_DATABASE": "airdata",
            "APP_MYSQL_USER": "readonly",
            "APP_MYSQL_PASSWORD": "readonly-secret",
            "MYSQL_SSL_DISABLED": "true",
        },
        clear=True,
    )
    @patch.object(dashboard.mysql.connector, "connect")
    def test_database_uses_dedicated_dashboard_credentials(self, connect):
        dashboard.connect_db()
        config = connect.call_args.kwargs
        self.assertEqual(config["user"], "readonly")
        self.assertEqual(config["password"], "readonly-secret")
        self.assertTrue(config["ssl_disabled"])


if __name__ == "__main__":
    unittest.main()
