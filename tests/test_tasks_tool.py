"""Tests for the tasks_tool module."""

from unittest.mock import patch, MagicMock

import pytest

try:
    from tasks_tool import add_task, list_tasks, get_tasks_service
except (ImportError, ModuleNotFoundError):
    pytest.skip("Google API libraries not available", allow_module_level=True)


class TestAddTask:
    """Tests for add_task."""

    @patch("tasks_tool.get_tasks_service")
    def test_add_task_success(self, mock_get_svc):
        """Add task returns success message."""
        mock_service = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute.return_value = {"title": "Buy groceries"}
        mock_service.tasks.return_value.insert.return_value = mock_insert
        mock_get_svc.return_value = mock_service

        result = add_task("Buy groceries", "Milk and eggs")
        assert "Successfully" in result
        assert "Buy groceries" in result

    @patch("tasks_tool.get_tasks_service")
    def test_add_task_without_notes(self, mock_get_svc):
        """Add task without notes should still work."""
        mock_service = MagicMock()
        mock_insert = MagicMock()
        mock_insert.execute.return_value = {"title": "Walk dog"}
        mock_service.tasks.return_value.insert.return_value = mock_insert
        mock_get_svc.return_value = mock_service

        result = add_task("Walk dog")
        assert "Successfully" in result

    @patch("tasks_tool.get_tasks_service")
    def test_add_task_error(self, mock_get_svc):
        """Error during add should be caught."""
        mock_get_svc.side_effect = Exception("API error")
        result = add_task("Test")
        assert "Failed" in result


class TestListTasks:
    """Tests for list_tasks."""

    @patch("tasks_tool.get_tasks_service")
    def test_list_with_tasks(self, mock_get_svc):
        """List returns formatted task list."""
        mock_service = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {
            "items": [
                {"title": "Task 1", "notes": "Note 1"},
                {"title": "Task 2", "notes": ""},
            ]
        }
        mock_service.tasks.return_value.list.return_value = mock_list
        mock_get_svc.return_value = mock_service

        result = list_tasks()
        assert "Task 1" in result
        assert "Task 2" in result
        assert "current tasks" in result.lower()

    @patch("tasks_tool.get_tasks_service")
    def test_list_empty(self, mock_get_svc):
        """List returns no-pending message."""
        mock_service = MagicMock()
        mock_list = MagicMock()
        mock_list.execute.return_value = {"items": []}
        mock_service.tasks.return_value.list.return_value = mock_list
        mock_get_svc.return_value = mock_service

        result = list_tasks()
        assert "no pending" in result.lower()

    @patch("tasks_tool.get_tasks_service")
    def test_list_error(self, mock_get_svc):
        """Error during list should be caught."""
        mock_get_svc.side_effect = Exception("Auth error")
        result = list_tasks()
        assert "Failed" in result
