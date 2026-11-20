import base64
import json

import numpy as np
import pytest

from api_server import app
from biomarker_tool import analyze_audio_biomarkers, reset_baseline
from config import config
from setup_db import setup_database
from sql_tool import execute_sql_query, get_database_schema


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_index_served(client):
    """1. Verify GET / serves index.html and contains Tinkr HTML markup."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    assert b"Tinkr" in response.data
    assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data.lower()


def test_health_endpoint(client):
    """2. Verify GET /api/health returns HTTP 200, valid schema, and no exposed secrets."""
    response = client.get("/api/health")
    assert response.status_code == 200

    data = response.get_json()
    assert data["status"] in ("ok", "degraded")
    assert data["service"] == "tinkr-api"
    assert isinstance(data["python_version"], str)

    # Database readiness
    assert isinstance(data["database"], dict)
    assert "connected" in data["database"]
    assert "path_exists" in data["database"]
    assert data["database"]["connected"] is True

    # OAuth check
    assert isinstance(data["google_oauth"], dict)
    assert "token_present" in data["google_oauth"]

    # Integrations boolean flags
    assert isinstance(data["integrations"], dict)
    for key, val in data["integrations"].items():
        assert isinstance(val, bool), f"Integration flag '{key}' must be boolean"

    # Secret leakage audit on response payload
    raw_text = response.get_data(as_text=True)
    for secret in config.get_sensitive_values():
        assert secret not in raw_text, f"Secret value leaked in /api/health payload: {secret}"


def test_config_defaults_safe():
    """3. Verify DEBUG defaults to False and diagnostics() returns booleans only."""
    assert config.DEBUG is False
    assert config.PORT == 5000
    assert config.DB_PATH.is_absolute()
    assert config.TOKEN_PATH.is_absolute()

    diag = config.diagnostics()
    assert isinstance(diag, dict)
    for key, val in diag.items():
        assert isinstance(val, bool), f"Diagnostic key '{key}' was not a boolean"


def test_database_seed_and_readonly_sql(tmp_path, monkeypatch):
    """4. Verify setup_db seeds schema into temporary DB and sql_tool restricts writes."""
    temp_db = tmp_path / "test_company_data.db"
    monkeypatch.setattr(config, "DB_PATH", temp_db)

    # Seed the database
    setup_database()
    assert temp_db.exists()

    # Verify schema introspection
    schema_raw = get_database_schema()
    schema = json.loads(schema_raw)
    assert "customers" in schema
    assert "products" in schema
    assert "sales" in schema
    assert "emotional_states" in schema

    # Verify SELECT queries are allowed
    select_res = execute_sql_query("SELECT count(*) as count FROM customers;")
    select_data = json.loads(select_res)
    assert isinstance(select_data, list)
    assert len(select_data) == 1
    assert select_data[0]["count"] > 0

    # Verify destructive mutations are blocked
    blocked_queries = [
        "DROP TABLE customers;",
        "DELETE FROM customers;",
        "UPDATE customers SET name = 'Attacker';",
        "INSERT INTO customers (name, region) VALUES ('Fake', 'Unknown');",
    ]
    for query in blocked_queries:
        res = execute_sql_query(query)
        res_data = json.loads(res)
        assert "error" in res_data
        assert "Only SELECT queries are allowed" in res_data["error"]


def test_biomarker_calibration_and_detection():
    """5. Verify biomarker calibration on 3 inputs, followed by anomaly detection on 4th input."""
    user_id = "test_phase0_user"
    reset_baseline(user_id)

    # 1 second of 16kHz sine wave (440 Hz) - calm/normal audio
    t = np.linspace(0, 1.0, 16000, False)
    calm_audio = (np.sin(t * 440 * 2 * np.pi) * 16384).astype(np.int16)
    calm_b64 = base64.b64encode(calm_audio.tobytes()).decode("ascii")

    # Feed 3 calibration samples
    for i in range(3):
        res = analyze_audio_biomarkers(calm_b64, user_id=user_id)
        assert isinstance(res, dict)
        assert res["alert"] is False
        assert "mean_zcr" in res
        assert "rms_variance" in res
        assert "suggestions" in res

    # Feed 4th high-variance / high-ZCR synthetic signal (rapid square-wave oscillation)
    high_zcr_audio = (np.sign(np.sin(t * 3500 * 2 * np.pi)) * 30000).astype(np.int16)
    # Add random amplitude bursts
    bursts = np.random.choice([0.1, 1.0], size=16000)
    high_zcr_audio = (high_zcr_audio * bursts).astype(np.int16)
    high_zcr_b64 = base64.b64encode(high_zcr_audio.tobytes()).decode("ascii")

    detection_res = analyze_audio_biomarkers(high_zcr_b64, user_id=user_id)
    assert isinstance(detection_res, dict)
    assert "predicted_state" in detection_res
    assert "alert" in detection_res
    assert "voice_energy_level" in detection_res
    assert "message" in detection_res
    assert "suggestions" in detection_res
