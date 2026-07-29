import os
import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

# Indian Standard Time offset
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_calendar_service():
    try:
        if not os.path.exists('token.json'):
            raise Exception("Calendar is not authenticated. Missing token.json.")
        
        creds = Credentials.from_authorized_user_file('token.json')
        
        # Explicitly refresh the token if expired
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
                
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        print(f"❌ CALENDAR AUTH ERROR: {e}")
        raise

def _parse_datetime_ist(date_str: str) -> datetime.datetime:
    """Parse an ISO datetime string and ensure it has IST timezone."""
    try:
        dt = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        # Convert to IST if it has timezone info
        if dt.tzinfo is not None:
            dt = dt.astimezone(IST)
        # Strip tzinfo so we return a naive datetime
        return dt.replace(tzinfo=None)
    except ValueError:
        pass

    # Fallback: strip timezone suffix and parse manually
    clean_str = date_str.split('+')[0].split('Z')[0]
    if '.' in clean_str:
        clean_str = clean_str.split('.')[0]

    if 'T' in clean_str:
        dt = datetime.datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S")
    else:
        dt = datetime.datetime.strptime(clean_str[:10], "%Y-%m-%d")

    # Return naive datetime so we can apply the calendar's native timezone
    return dt

def check_availability(date_iso: str) -> str:
    """Checks Google Calendar for busy slots on a specific date."""
    try:
        service = get_calendar_service()
        dt = _parse_datetime_ist(date_iso)

        start_of_day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = dt.replace(hour=23, minute=59, second=59, microsecond=0)
        
        calendar_id = os.getenv("HOST_CALENDAR_ID", "primary")
        
        # Fetch the calendar's timezone
        cal_tz = 'UTC'
        try:
            cal_meta = service.calendars().get(calendarId=calendar_id).execute()
            cal_tz = cal_meta.get('timeZone', 'UTC')
        except Exception:
            pass
        
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy='startTime',
            timeZone=cal_tz
        ).execute()
        
        events = events_result.get('items', [])
        
        if not events:
            return f"The calendar is completely free on {dt.strftime('%A, %B %d, %Y')}."
            
        busy_times = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            end = event['end'].get('dateTime', event['end'].get('date'))
            summary = event.get('summary', 'Busy')
            busy_times.append(f"- {summary}: {start} to {end}")
            
        return f"Existing events on {dt.strftime('%A, %B %d, %Y')}:\n" + "\n".join(busy_times)
        
    except Exception as e:
        print(f"❌ CALENDAR ERROR: {e}")
        return f"Failed to check availability: {str(e)}"

def book_meeting(date_time_iso: str, name: str = "User") -> str:
    """Creates a 30-minute Google Calendar meeting."""
    try:
        service = get_calendar_service()
        start_time = _parse_datetime_ist(date_time_iso)
        end_time = start_time + datetime.timedelta(minutes=30)
        calendar_id = os.getenv("HOST_CALENDAR_ID", "primary")

        # Fetch the calendar's native timezone so the event visually aligns
        cal_tz = 'UTC'
        try:
            cal_meta = service.calendars().get(calendarId=calendar_id).execute()
            cal_tz = cal_meta.get('timeZone', 'UTC')
        except Exception:
            pass

        event = {
            'summary': f'Meeting: {name}',
            'description': 'Automated booking created via Tinkr Voice Assistant.',
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': cal_tz,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': cal_tz,
            },
        }

        event_result = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"✅ CALENDAR BOOKING SUCCESS: {event_result.get('htmlLink')}")
        return f"Success! Meeting '{name}' booked for {start_time.strftime('%I:%M %p on %A, %B %d, %Y')}."
        
    except Exception as e:
        print(f"❌ CALENDAR ERROR: {e}")
        return f"Failed to book meeting: {str(e)}"

def set_reminder(title: str, date_time_iso: str) -> str:
    """Creates a short 15-minute event as a reminder on Google Calendar."""
    try:
        service = get_calendar_service()
        start_time = _parse_datetime_ist(date_time_iso)
        end_time = start_time + datetime.timedelta(minutes=15)
        calendar_id = os.getenv("HOST_CALENDAR_ID", "primary")

        # Fetch the calendar's native timezone
        cal_tz = 'UTC'
        try:
            cal_meta = service.calendars().get(calendarId=calendar_id).execute()
            cal_tz = cal_meta.get('timeZone', 'UTC')
        except Exception:
            pass

        event = {
            'summary': f'Reminder: {title}',
            'description': 'Automated reminder created via Tinkr Voice Assistant.',
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': cal_tz,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': cal_tz,
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 10},
                ],
            },
        }

        event_result = service.events().insert(calendarId=calendar_id, body=event).execute()
        print(f"✅ CALENDAR REMINDER SUCCESS: {event_result.get('htmlLink')}")
        return f"Success! Reminder '{title}' set for {start_time.strftime('%I:%M %p on %A, %B %d, %Y')}."
        
    except Exception as e:
        print(f"❌ CALENDAR REMINDER ERROR: {e}")
        return f"Failed to set reminder: {str(e)}"