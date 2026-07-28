"""Tests for the calendar_tool module."""

from unittest.mock import patch, MagicMock

import pytest

# The module has heavy google deps; skip if not available
try:
    from calendar_tool import _parse_datetime, check_availability, book_meeting, get_calendar_service
except (ImportError, ModuleNotFoundError):
    pytest.skip("Google API libraries not available", allow_module_level=True)

import datetime


class TestParseDatetime:
    """Tests for the _parse_datetime helper."""

    def test_iso_with_tz(self):
        """Parse ISO 8601 with timezone offset."""
        dt = _parse_datetime("2026-07-28T10:00:00+05:30")
        assert dt.year == 2026
        assert dt.month == 7
        assert dt.day == 28

    def test_iso_with_z(self):
        """Parse ISO 8601 with Z suffix."""
        dt = _parse_datetime("2026-07-28T10:00:00Z")
        assert dt.hour == 10
        assert dt.minute == 0

    def test_date_only(self):
        """Parse date-only string."""
        dt = _parse_datetime("2026-07-28")
        assert dt.month == 7
        assert dt.day == 28
        assert dt.hour == 0

    def test_datetime_with_millis(self):
        """Parse datetime with milliseconds."""
        dt = _parse_datetime("2026-07-28T10:00:00.123")
        assert dt.second == 0

    def test_simple_iso(self):
        """Parse simple ISO without tz."""
        dt = _parse_datetime("2026-07-28T10:00:00")
        assert dt.hour == 10

    def test_different_date(self):
        """Parse a different date correctly."""
        dt = _parse_datetime("2025-01-15")
        assert dt.month == 1
        assert dt.day == 15
        assert dt.year == 2025


class TestCheckAvailability:
    """Tests for check_availability."""

    @patch("calendar_tool.get_calendar_service")
    def test_free_day(self, mock_get_svc):
        """Returns free message when no events."""
        mock_service = MagicMock()
        mock_events = MagicMock()
        mock_events.list.return_value.execute.return_value = {"items": []}
        mock_service.events.return_value = mock_events
        mock_get_svc.return_value = mock_service

        result = check_availability("2026-07-28")
        assert "completely free" in result.lower()

    @patch("calendar_tool.get_calendar_service")
    def test_busy_day(self, mock_get_svc):
        """Returns busy times when events exist."""
        mock_service = MagicMock()
        mock_events = MagicMock()
        mock_events.list.return_value.execute.return_value = {
            "items": [
                {
                    "summary": "Team standup",
                    "start": {"dateTime": "2026-07-28T09:00:00"},
                    "end": {"dateTime": "2026-07-28T09:30:00"},
                }
            ]
        }
        mock_service.events.return_value = mock_events
        mock_get_svc.return_value = mock_service

        result = check_availability("2026-07-28")
        assert "Blocked" in result
        assert "Team standup" in result

    @patch("calendar_tool.get_calendar_service")
    def test_service_error(self, mock_get_svc):
        """Error in service should be caught."""
        mock_get_svc.side_effect = Exception("Auth error")
        result = check_availability("2026-07-28")
        assert "Failed" in result or "Error" in result

    @patch("calendar_tool.os.path.exists")
    @patch("calendar_tool.build")
    def test_missing_token(self, mock_build, mock_exists):
        """Missing token.json should raise."""
        mock_exists.return_value = False
        with pytest.raises(Exception, match="Missing token.json"):
            get_calendar_service()
