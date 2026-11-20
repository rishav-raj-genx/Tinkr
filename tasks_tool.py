from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from config import config
from logger import get_logger

logger = get_logger("tasks_tool")


def get_tasks_service():
    if not config.TOKEN_PATH.exists():
        raise RuntimeError(f"Tasks is not authenticated. Missing token file at {config.TOKEN_PATH}.")

    creds = Credentials.from_authorized_user_file(str(config.TOKEN_PATH))

    # Explicitly refresh the token if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        config.save_token_json(creds.to_json())

    return build("tasks", "v1", credentials=creds)


def add_task(title: str, notes: str = "") -> str:
    """Adds a new task to the user's primary task list."""
    try:
        service = get_tasks_service()
        task = {
            "title": title,
            "notes": notes,
        }
        result = service.tasks().insert(tasklist="@default", body=task).execute()
        return f"Successfully added task: '{result.get('title')}'"
    except Exception as e:
        logger.error("Failed to add task: %s", e)
        return f"Failed to add task: {e!s}"


def list_tasks() -> str:
    """Lists the top 10 pending tasks from the user's primary task list."""
    try:
        service = get_tasks_service()
        results = service.tasks().list(tasklist="@default", maxResults=10, showCompleted=False).execute()
        items = results.get("items", [])

        if not items:
            return "You have no pending tasks."

        task_list = []
        for item in items:
            task_list.append(f"- {item['title']} (Notes: {item.get('notes', 'None')})")

        return "Your current tasks:\n" + "\n".join(task_list)
    except Exception as e:
        logger.error("Failed to list tasks: %s", e)
        return f"Failed to list tasks: {e!s}"
