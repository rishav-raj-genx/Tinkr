from api_server import app
from config import config


def test_health_endpoint():
    """Verify GET /api/health returns HTTP 200 and valid non-sensitive diagnostic payload."""
    client = app.test_client()
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()

    assert data["status"] in ("ok", "degraded")
    assert data["service"] == "tinkr-api"
    assert isinstance(data["python_version"], str)

    # Database diagnostics
    assert isinstance(data["database"], dict)
    assert isinstance(data["database"]["connected"], bool)
    assert isinstance(data["database"]["path_exists"], bool)
    assert data["database"]["connected"] is True

    # OAuth diagnostics
    assert isinstance(data["google_oauth"], dict)
    assert isinstance(data["google_oauth"]["token_present"], bool)

    # Integrations diagnostics
    assert isinstance(data["integrations"], dict)
    for key, val in data["integrations"].items():
        assert isinstance(val, bool), f"Integration key {key} must be a boolean"

    # Leak verification: ensure no sensitive keys are present
    raw_response_text = response.get_data(as_text=True)
    sensitive_values = config.get_sensitive_values()
    for secret in sensitive_values:
        assert secret not in raw_response_text, f"Secret leaked in health response: {secret}"


def test_config_defaults():
    """Verify Config defaults to secure settings."""
    assert config.DEBUG is False
    assert config.PORT == 5000
    assert config.DB_PATH.is_absolute()
    assert config.TOKEN_PATH.is_absolute()
