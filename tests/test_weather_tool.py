"""Tests for the weather_tool module."""

import json
from unittest.mock import patch, MagicMock

import pytest
from weather_tool import get_weather


class TestGetWeather:
    """Tests for the get_weather function."""

    def test_missing_api_key(self):
        """Returns error JSON when WEATHER_API_KEY is not set."""
        with patch.dict("os.environ", {}, clear=True):
            result = get_weather("London")
            data = json.loads(result)
            assert "error" in data
            assert "API key" in data["error"]

    @patch("weather_tool.requests")
    def test_location_not_found(self, mock_requests):
        """Returns error when API returns 404."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_requests.get.return_value = mock_response

        with patch.dict("os.environ", {"WEATHER_API_KEY": "test_key"}):
            result = get_weather("Atlantis")
            data = json.loads(result)
            assert "error" in data
            assert "not found" in data["error"].lower()

    @patch("weather_tool.requests")
    def test_api_error(self, mock_requests):
        """Returns error when API returns non-200."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_requests.get.return_value = mock_response

        with patch.dict("os.environ", {"WEATHER_API_KEY": "test_key"}):
            result = get_weather("London")
            data = json.loads(result)
            assert "error" in data

    @pytest.mark.network
    @patch("weather_tool.requests")
    def test_successful_weather_fetch(self, mock_requests):
        """Returns structured weather data when API succeeds."""
        # Mock current weather response
        mock_curr = MagicMock()
        mock_curr.status_code = 200
        mock_curr.json.return_value = {
            "name": "London",
            "main": {"temp": 15.5},
            "weather": [{"description": "clear sky"}],
        }

        # Mock forecast response
        mock_fore = MagicMock()
        mock_fore.status_code = 200
        mock_fore.json.return_value = {
            "list": [
                {"dt_txt": "2026-07-28 12:00:00", "main": {"temp": 16.0}, "weather": [{"description": "partly cloudy"}]},
                {"dt_txt": "2026-07-28 15:00:00", "main": {"temp": 14.5}, "weather": [{"description": "cloudy"}]},
            ]
        }

        def get_side_effect(url, **kwargs):
            if "forecast" in url:
                return mock_fore
            return mock_curr

        mock_requests.get.side_effect = get_side_effect

        with patch.dict("os.environ", {"WEATHER_API_KEY": "test_key"}):
            result = get_weather("London")
            data = json.loads(result)
            assert data["location"] == "London"
            assert len(data["forecast_next_12h"]) == 2
            assert data["forecast_next_12h"][0]["temp"] == 16.0

    @patch("weather_tool.requests")
    def test_network_error(self, mock_requests):
        """Returns error JSON when request raises an exception."""
        import requests as real_requests
        mock_requests.get.side_effect = real_requests.ConnectionError("Network error")

        with patch.dict("os.environ", {"WEATHER_API_KEY": "test_key"}):
            result = get_weather("London")
            data = json.loads(result)
            assert "error" in data
            assert "Network error" in data["error"]
