import importlib


def test_core_imports():
    """Verify core tool modules can be imported without syntax or import errors."""
    modules = [
        "biomarker_tool",
        "calendar_tool",
        "tasks_tool",
        "weather_tool",
        "web_tool",
        "sql_tool",
        "setup_db",
    ]
    for mod in modules:
        imported = importlib.import_module(mod)
        assert imported is not None


def test_biomarker_calibration_structure():
    """Verify biomarker module initializes calm response structure correctly."""
    from biomarker_tool import _make_calm_result

    res = _make_calm_result(voice_energy_level="medium", message="Calibrating")
    assert res["alert"] is False
    assert res["predicted_state"] == "calm"
    assert res["voice_energy_level"] == "medium"
    assert res["message"] == "Calibrating"
