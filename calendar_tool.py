import os
import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

def get_calendar_service():
    if not os.path.exists('token.json'):
        raise Exception("Calendar is not authenticated. Missing token.json.")
    creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/tasks'])
    return build('calendar', 'v3', credentials=creds)

def check_availability(date_iso: str) -> str:
    """Checks Google Calendar for busy slots on a specific date."""
    try:
        service = get_calendar_service()
        
        # Cross-platform / cross-version robust ISO datetime parsing
        try:
            dt = datetime.datetime.fromisoformat(date_iso.replace('Z', '+00:00'))
        except ValueError:
            # Clean string format fallback if older Python versions struggle with suffix colons or milliseconds
            clean_str = date_iso.split('.')[0].split('+')[0].split('-')[0]
            if len(clean_str) > 10:
                dt = datetime.datetime.strptime(clean_str[:19], "%Y-%m-%dT%H:%M:%S")
            else:
                dt = datetime.datetime.strptime(clean_str[:10], "%Y-%m-%d")
        
        start_of_day = dt.replace(hour=0, minute=0, second=0).isoformat()
        end_of_day = dt.replace(hour=23, minute=59, second=59).isoformat()
        
        calendar_id = os.getenv("HOST_CALENDAR_ID", "primary")
        
        events_result = service.events().list(
            calendarId=calendar_id, timeMin=start_of_day, timeMax=end_of_day, 
            singleEvents=True, orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return f"The calendar is completely free on {dt.strftime('%Y-%m-%d')}."
            
        busy_times = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            summary = event.get('summary', 'Busy')
            busy_times.append(f"- Blocked from {start} to {end} ({summary})")
            
        return f"Existing events on {dt.strftime('%Y-%m-%d')}:\n" + "\n".join(busy_times)
        
    except Exception as e:
        print(f"❌ CALENDAR ERROR: {e}")
        return f"Failed to check availability: {str(e)}"

def book_meeting(date_time_iso: str, name: str = "User") -> str:
    """Creates a 30-minute Google Calendar meeting."""
    try:
        service = get_calendar_service()
        
        # Cross-platform / cross-version robust ISO datetime parsing
        try:
            start_time = datetime.datetime.fromisoformat(date_time_iso.replace('Z', '+00:00'))
        except ValueError:
            clean_str = date_time_iso.split('.')[0].split('+')[0].split('-')[0]
            start_time = datetime.datetime.strptime(clean_str[:19], "%Y-%m-%dT%H:%M:%S")
            
        end_time = start_time + datetime.timedelta(minutes=30)
        calendar_id = os.getenv("HOST_CALENDAR_ID", "primary")

        event = {
            'summary': f'NovaVoice Demo: {name}',
            'description': 'Automated booking created via Gemini Live AI Calling Assistant.',
            'start': {'dateTime': start_time.isoformat()},
            'end': {'dateTime': end_time.isoformat()},
        }

        event_result = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"✅ REAL CALENDAR BOOKING SUCCESS: {event_result.get('htmlLink')}")
        return f"Success! Meeting booked on Google Calendar for {name}."
        
    except Exception as e:
        print(f"❌ CALENDAR ERROR: {e}")
        return f"Failed to book meeting: {str(e)}"