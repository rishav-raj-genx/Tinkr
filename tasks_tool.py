import os
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

def get_tasks_service():
    if not os.path.exists('token.json'):
        raise Exception("Tasks is not authenticated. Missing token.json.")
    
    creds = Credentials.from_authorized_user_file('token.json')
    
    # Explicitly refresh the token if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('tasks', 'v1', credentials=creds)

def add_task(title: str, notes: str = "") -> str:
    """Adds a new task to the user's primary task list."""
    try:
        service = get_tasks_service()
        task = {
            'title': title,
            'notes': notes
        }
        result = service.tasks().insert(tasklist='@default', body=task).execute()
        return f"Successfully added task: '{result.get('title')}'"
    except Exception as e:
        print(f"❌ TASKS ERROR: {e}")
        return f"Failed to add task: {str(e)}"

def list_tasks() -> str:
    """Lists the top 10 pending tasks from the user's primary task list."""
    try:
        service = get_tasks_service()
        results = service.tasks().list(tasklist='@default', maxResults=10, showCompleted=False).execute()
        items = results.get('items', [])
        
        if not items:
            return "You have no pending tasks."
            
        task_list = []
        for item in items:
            task_list.append(f"- {item['title']} (Notes: {item.get('notes', 'None')})")
            
        return "Your current tasks:\n" + "\n".join(task_list)
    except Exception as e:
        print(f"❌ TASKS ERROR: {e}")
        return f"Failed to list tasks: {str(e)}"
