import os
import json
import sqlite3
import traceback
import base64
from datetime import datetime, timezone
from email.message import EmailMessage

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from openai import OpenAI
from groq import Groq
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# Tool modules
from biomarker_tool import analyze_audio_biomarkers
from calendar_tool import book_meeting, check_availability, set_reminder
from tasks_tool import add_task, list_tasks
from web_tool import search_web, get_news
from weather_tool import get_weather

load_dotenv()

app = Flask(__name__)
CORS(app)

# ── In-memory chat history (per session, not persisted) ──
chat_histories = {}      # user_id -> list of message dicts

# ── SQLite DB Path ──
DB_PATH = 'company_data.db'


def get_db():
    """Get a SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def save_emotional_state_db(user_id, predicted_state, user_confirmed, mean_zcr,
                            rms_variance, voice_energy_level, suggestions):
    """Save an emotional state to the database and return its ID."""
    conn = get_db()
    try:
        cursor = conn.execute(
            '''INSERT INTO emotional_states
               (user_id, predicted_state, user_confirmed, mean_zcr, rms_variance,
                voice_energy_level, suggestions, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, predicted_state, user_confirmed, mean_zcr, rms_variance,
             voice_energy_level, json.dumps(suggestions),
             datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_emotional_history_db(user_id, limit=20):
    """Get the emotional state history for a user from the database."""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT id, predicted_state, user_confirmed, mean_zcr, rms_variance,
                      voice_energy_level, suggestions, timestamp
               FROM emotional_states
               WHERE user_id = ?
               ORDER BY id DESC LIMIT ?''',
            (user_id, limit)
        ).fetchall()
        result = []
        for row in rows:
            entry = dict(row)
            try:
                entry['suggestions'] = json.loads(entry['suggestions'])
            except (json.JSONDecodeError, TypeError):
                entry['suggestions'] = []
            result.append(entry)
        return result
    finally:
        conn.close()


def save_emotional_chat_db(user_id, emotional_state_id, role, content):
    """Save a chat message linked to an emotional state."""
    conn = get_db()
    try:
        conn.execute(
            '''INSERT INTO emotional_chats
               (user_id, emotional_state_id, role, content, timestamp)
               VALUES (?, ?, ?, ?, ?)''',
            (user_id, emotional_state_id, role, content,
             datetime.now(timezone.utc).isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def get_emotional_chats_db(emotional_state_id):
    """Get all chat messages for a specific emotional state."""
    conn = get_db()
    try:
        rows = conn.execute(
            '''SELECT role, content, timestamp
               FROM emotional_chats
               WHERE emotional_state_id = ?
               ORDER BY id ASC''',
            (emotional_state_id,)
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_full_emotional_chat_history_db(user_id, limit=20):
    """Get emotional states with their associated chat messages for a user."""
    conn = get_db()
    try:
        states = conn.execute(
            '''SELECT id, predicted_state, user_confirmed, mean_zcr, rms_variance,
                      voice_energy_level, suggestions, timestamp
               FROM emotional_states
               WHERE user_id = ? AND user_confirmed = 1
               ORDER BY id DESC LIMIT ?''',
            (user_id, limit)
        ).fetchall()
        result = []
        for state in states:
            entry = dict(state)
            try:
                entry['suggestions'] = json.loads(entry['suggestions'])
            except (json.JSONDecodeError, TypeError):
                entry['suggestions'] = []
            chats = conn.execute(
                '''SELECT role, content, timestamp
                   FROM emotional_chats
                   WHERE emotional_state_id = ?
                   ORDER BY id ASC''',
                (entry['id'],)
            ).fetchall()
            entry['chats'] = [dict(c) for c in chats]
            result.append(entry)
        return result
    finally:
        conn.close()

# ── LLM Client (Gemma 4 via Google AI Studio) ──
client = OpenAI(
    api_key=os.environ.get("API_KEY", "dummy_key"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
MODEL_NAME = "gemma-4-26b-a4b-it"

# ── Groq Whisper STT Client ──
groq_client = Groq(
    api_key=os.environ.get("GROQ_API_KEY", "dummy_key")
)


# ═══════════════════════════════════════════════════════════════
# Gmail Tool Functions
# ═══════════════════════════════════════════════════════════════

def get_gmail_service():
    if not os.path.exists('token.json'):
        raise Exception("Missing token.json. Run auth_server.py first.")
    creds = Credentials.from_authorized_user_file('token.json')
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)


def check_unread_emails(timeframe="today"):
    try:
        service = get_gmail_service()
        query = "is:unread"
        if timeframe == "today":
            query += " newer_than:1d"
        results = service.users().messages().list(userId='me', q=query, maxResults=5).execute()
        messages = results.get('messages', [])
        if not messages:
            return "You have no unread emails."

        email_summaries = []
        for msg in messages:
            msg_data = service.users().messages().get(
                userId='me', id=msg['id'], format='metadata',
                metadataHeaders=['From', 'Subject']
            ).execute()
            headers = msg_data.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
            snippet = msg_data.get('snippet', '')
            email_summaries.append(f"From: {sender}\nSubject: {subject}\nSnippet: {snippet}")

        return "Unread emails:\n" + "\n\n".join(email_summaries)
    except Exception as e:
        return f"Failed to check emails: {str(e)}"


def draft_email(recipient_email, subject, body_context):
    try:
        service = get_gmail_service()
        message = EmailMessage()
        message.set_content(body_context)
        message['To'] = recipient_email
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'message': {'raw': encoded_message}}

        draft = service.users().drafts().create(userId='me', body=create_message).execute()
        return f"Draft created successfully. Draft ID: {draft['id']}"
    except Exception as e:
        return f"Failed to draft email: {str(e)}"


def send_email(recipient_email, subject, body_context):
    try:
        service = get_gmail_service()
        message = EmailMessage()
        message.set_content(body_context)
        message['To'] = recipient_email
        message['Subject'] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_message = {'raw': encoded_message}

        sent = service.users().messages().send(userId='me', body=send_message).execute()
        return f"Email sent successfully to {recipient_email}. Message ID: {sent['id']}"
    except Exception as e:
        return f"Failed to send email: {str(e)}"


# ═══════════════════════════════════════════════════════════════
# Gemma 4 Tool Definitions
# ═══════════════════════════════════════════════════════════════

tools = [
    {
        "type": "function",
        "function": {
            "name": "check_availability",
            "description": "Checks the user's calendar for busy slots on a given day.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "ISO 8601 date to check (e.g., 2026-05-26T00:00:00+05:30)"}
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_meeting",
            "description": "Schedules a meeting on the calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Meeting title"},
                    "date_time": {"type": "string", "description": "ISO 8601 date and time (e.g., 2026-05-26T09:00:00+05:30)"},
                    "guest_name": {"type": "string", "description": "Optional name or identifier of the guest"}
                },
                "required": ["title", "date_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": "Sets a reminder on the calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Reminder title"},
                    "date_time": {"type": "string", "description": "ISO 8601 date and time (e.g., 2026-05-26T09:00:00+05:30)"}
                },
                "required": ["title", "date_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Searches the web for general information. DO NOT use this for weather or news.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Fetches the latest news headlines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The news topic"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Fetches current weather for a specified location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Adds a new task to the user's to-do list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Task title"},
                    "notes": {"type": "string", "description": "Optional notes for the task"}
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Lists the user's current pending tasks and to-do items.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_unread_emails",
            "description": "Checks the user's Gmail for unread emails.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timeframe": {"type": "string", "description": "Timeframe to check for unread emails (e.g., 'today')"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "draft_email",
            "description": "Creates a draft email in the user's Gmail. Use this when the user wants to draft or prepare an email without sending it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient_email": {"type": "string", "description": "The email address of the recipient"},
                    "subject": {"type": "string", "description": "The subject of the email"},
                    "body_context": {"type": "string", "description": "The body content of the email"}
                },
                "required": ["recipient_email", "subject", "body_context"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Sends an email immediately via the user's Gmail. Use this when the user explicitly says 'send' an email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient_email": {"type": "string", "description": "The email address of the recipient"},
                    "subject": {"type": "string", "description": "The subject of the email"},
                    "body_context": {"type": "string", "description": "The body content of the email"}
                },
                "required": ["recipient_email", "subject", "body_context"]
            }
        }
    }
]

# Tool name -> handler function mapping
TOOL_HANDLERS = {
    "check_availability": lambda args: str(check_availability(date_iso=args.get("date"))),
    "book_meeting": lambda args: str(book_meeting(date_time_iso=args.get("date_time"), name=args.get("guest_name", args.get("title", "Meeting")))),
    "set_reminder": lambda args: str(set_reminder(title=args.get("title"), date_time_iso=args.get("date_time"))),
    "search_web": lambda args: str(search_web(query=args.get("query"))),
    "get_news": lambda args: str(get_news(query=args.get("query"))),
    "get_weather": lambda args: str(get_weather(location=args.get("location"))),
    "add_task": lambda args: str(add_task(title=args.get("title"), notes=args.get("notes", ""))),
    "list_tasks": lambda args: str(list_tasks()),
    "check_unread_emails": lambda args: str(check_unread_emails(timeframe=args.get("timeframe", "today"))),
    "draft_email": lambda args: str(draft_email(recipient_email=args.get("recipient_email"), subject=args.get("subject"), body_context=args.get("body_context"))),
    "send_email": lambda args: str(send_email(recipient_email=args.get("recipient_email"), subject=args.get("subject"), body_context=args.get("body_context"))),
}

TRIGGER_WORDS = [
    "calendar", "schedule", "book", "news", "search", "weather",
    "task", "todo", "meeting", "remind", "reminder", "list", "pending",
    "email", "mail", "draft", "inbox", "send", "unread",
]


# ═══════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════

@app.route('/api/transcribe', methods=['POST'])
def handle_transcribe():
    """Receives audio from the frontend and transcribes it using Groq Whisper."""
    print("\n--- PIPELINE STEP 1: STT ---")
    if 'audio' not in request.files:
        print(" [STT ERROR] No audio file provided in request.")
        return jsonify({"success": False, "message": "No audio file provided"}), 400

    audio_file = request.files['audio']
    temp_path = "/tmp/temp_audio.webm"
    audio_file.save(temp_path)

    try:
        with open(temp_path, "rb") as file:
            transcription = groq_client.audio.transcriptions.create(
                file=(temp_path, file.read()),
                model="whisper-large-v3-turbo",
                response_format="text"
            )
        text = transcription
        print(f" [STT SUCCESS] Transcribed: '{text}'")
    except Exception as e:
        print(f" [STT ERROR] Transcription failed: {e}")
        return jsonify({"success": False, "message": "Could not transcribe audio"}), 500

    return jsonify({"success": True, "text": text})


@app.route('/api/chat_stream', methods=['POST'])
def handle_chat_stream():
    """Primary streaming endpoint. Handles tool calls and streams the final LLM response via SSE."""
    data = request.json
    user_text = data.get('text', '')
    user_id = data.get('user_id', 'user')
    emotion_context = data.get('emotion_context', '')

    if user_id not in chat_histories:
        chat_histories[user_id] = []

    current_time = datetime.now().astimezone().isoformat()

    # Build wellness instruction only when emotion context is present
    wellness_instruction = ""
    if emotion_context and emotion_context.strip():
        wellness_instruction = f"""

IMPORTANT WELLNESS ALERT: The user has CONFIRMED they are experiencing emotional distress. You MUST:
1. FIRST acknowledge their emotional state warmly and empathetically before anything else.
2. Offer genuine comfort and support. Speak like a caring friend, not a robot.
3. Suggest one or two small, actionable things they can do right now to feel better.
4. Then, if they asked a question, answer it briefly.

{emotion_context}"""

    system_prompt = f"""You are Tinkr, an autonomous AI companion. You have access to tools for checking Google Calendar, searching the web, checking unread emails, drafting emails, and sending emails. If the user provides explicit email addresses or names via the text fallback box, prioritize that structured data for email operations. When the user says 'send' an email, use send_email. When they say 'draft', use draft_email.
Your core reasoning engine is Gemma 4. Keep all spoken responses extremely concise, conversational, and under 2 sentences unless detailed information is requested.
The user's name/ID is "{user_id}".
The current date and time is: {current_time}.
The user's timezone is Indian Standard Time (IST, UTC+05:30). Always use +05:30 offset in ISO 8601 dates.
Use book_meeting for meetings. Use set_reminder for setting calendar reminders.
When a tool returns information (like web search or weather), NEVER read out raw data, JSON, or lists verbatim. Summarize the answer conversationally in 1-2 natural sentences.
Do NOT use markdown formatting (like asterisks **, hashtags #, etc.). Keep the output as plain conversational text.
If the user asks for the weather without specifying a location, ask them for their city.
If any tool returns an error, you MUST explicitly tell the user what went wrong in a friendly way.{wellness_instruction}"""

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_histories[user_id])
    messages.append({"role": "user", "content": user_text})

    # Intent-Based Tool Bypass
    text_lower = user_text.lower()
    needs_tools = any(word in text_lower for word in TRIGGER_WORDS)
    active_tools = tools if needs_tools else None

    def generate():
        try:
            if active_tools:
                response = client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=messages,
                    tools=active_tools,
                    tool_choice="auto"
                )
                response_message = response.choices[0].message
                if response_message.tool_calls:
                    messages.append(response_message)
                    for tool_call in response_message.tool_calls:
                        function_name = tool_call.function.name
                        try:
                            function_args = json.loads(tool_call.function.arguments)
                            handler = TOOL_HANDLERS.get(function_name)
                            if handler:
                                function_response = handler(function_args)
                            else:
                                function_response = f"Error: Unknown tool '{function_name}'. Please tell the user this action is not supported."
                        except Exception as ex:
                            function_response = f"Error executing tool: {ex}"

                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": function_response,
                        })

            # Stream the final response
            stream_response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                stream=True
            )

            full_text = ""
            in_thought = False
            thought_buffer = ""
            for chunk in stream_response:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        thought_buffer += delta

                        while thought_buffer:
                            if in_thought:
                                end_thought = thought_buffer.find("</thought>")
                                end_think = thought_buffer.find("</think>")
                                end_idx = max(end_thought, end_think)
                                if end_idx != -1:
                                    in_thought = False
                                    tag_len = 10 if end_thought != -1 else 8
                                    thought_buffer = thought_buffer[end_idx + tag_len:]
                                else:
                                    thought_buffer = ""
                            else:
                                start_thought = thought_buffer.find("<thought>")
                                start_think = thought_buffer.find("<think>")

                                start_idx = -1
                                if start_thought != -1 and start_think != -1:
                                    start_idx = min(start_thought, start_think)
                                elif start_thought != -1:
                                    start_idx = start_thought
                                elif start_think != -1:
                                    start_idx = start_think

                                if start_idx != -1:
                                    safe_text = thought_buffer[:start_idx]
                                    if safe_text:
                                        full_text += safe_text
                                        yield f"data: {json.dumps({'text': safe_text})}\n\n"
                                    thought_buffer = thought_buffer[start_idx:]
                                    in_thought = True
                                else:
                                    if '<' in thought_buffer:
                                        break
                                    else:
                                        full_text += thought_buffer
                                        yield f"data: {json.dumps({'text': thought_buffer})}\n\n"
                                        thought_buffer = ""

            if thought_buffer and not in_thought and '<' not in thought_buffer:
                full_text += thought_buffer
                yield f"data: {json.dumps({'text': thought_buffer})}\n\n"

            chat_histories[user_id].append({"role": "user", "content": user_text})
            chat_histories[user_id].append({"role": "assistant", "content": full_text.strip()})

        except Exception as e:
            traceback.print_exc()
            print(f" [CHAT STREAM ERROR] {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


# ═══════════════════════════════════════════════════════════════
# Biomarker & Wellness Endpoints
# ═══════════════════════════════════════════════════════════════

@app.route('/api/analyze_audio', methods=['POST'])
def handle_analyze_audio():
    print("\n--- PIPELINE STEP 2: EMOTION TRACKING ---")
    data = request.json
    user_id = data.get('user_id', 'default')
    try:
        result = analyze_audio_biomarkers(
            base64_audio=data.get('audio_base64'),
            user_id=user_id
        )
        print(f" [EMOTION SUCCESS] [{user_id}] Alert: {result.get('alert')} | State: {result.get('predicted_state')}")
        return jsonify(result)
    except Exception as e:
        print(f" [EMOTION ERROR] Failed to analyze audio biomarkers: {e}")
        return jsonify({"alert": False, "error": str(e)})


@app.route('/api/save_mental_state', methods=['POST'])
def handle_save_mental_state():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"success": False, "message": "user_id is required."}), 400

    try:
        state_id = save_emotional_state_db(
            user_id=user_id,
            predicted_state=data.get("predicted_state", "unknown"),
            user_confirmed=data.get("user_confirmed", False),
            mean_zcr=data.get("mean_zcr", 0.0),
            rms_variance=data.get("rms_variance", 0.0),
            voice_energy_level=data.get("voice_energy_level", "medium"),
            suggestions=data.get("suggestions", [])
        )
        print(f" [DB STATE] Saved emotional state for '{user_id}': {data.get('predicted_state')} (id={state_id})")
        return jsonify({"success": True, "message": "Mental state saved successfully.", "state_id": state_id})
    except Exception as e:
        print(f" [DB ERROR] Failed to save emotional state: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/get_mental_state_history', methods=['POST'])
def handle_get_mental_state_history():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"success": False, "history": [], "message": "user_id is required."}), 400

    limit = data.get("limit", 20)
    try:
        history = get_emotional_history_db(user_id, limit)
        return jsonify({"success": True, "history": history})
    except Exception as e:
        print(f" [DB ERROR] Failed to fetch history: {e}")
        return jsonify({"success": False, "history": [], "message": str(e)}), 500


@app.route('/api/save_emotional_chat', methods=['POST'])
def handle_save_emotional_chat():
    """Save a user+assistant chat pair linked to an emotional state."""
    data = request.json
    user_id = data.get('user_id')
    state_id = data.get('emotional_state_id')
    user_message = data.get('user_message', '')
    assistant_message = data.get('assistant_message', '')

    if not user_id or not state_id:
        return jsonify({"success": False, "message": "user_id and emotional_state_id are required."}), 400

    try:
        if user_message:
            save_emotional_chat_db(user_id, state_id, 'user', user_message)
        if assistant_message:
            save_emotional_chat_db(user_id, state_id, 'assistant', assistant_message)
        print(f" [DB CHAT] Saved emotional chat for state_id={state_id}")
        return jsonify({"success": True})
    except Exception as e:
        print(f" [DB ERROR] Failed to save emotional chat: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/get_emotional_chats', methods=['POST'])
def handle_get_emotional_chats():
    """Get chat messages for a specific emotional state."""
    data = request.json
    state_id = data.get('emotional_state_id')
    if not state_id:
        return jsonify({"success": False, "chats": [], "message": "emotional_state_id is required."}), 400

    try:
        chats = get_emotional_chats_db(state_id)
        return jsonify({"success": True, "chats": chats})
    except Exception as e:
        return jsonify({"success": False, "chats": [], "message": str(e)}), 500


@app.route('/api/get_emotional_chat_history', methods=['POST'])
def handle_get_emotional_chat_history():
    """Get all confirmed emotional states with their chat messages for a user."""
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"success": False, "history": [], "message": "user_id is required."}), 400

    limit = data.get("limit", 20)
    try:
        history = get_full_emotional_chat_history_db(user_id, limit)
        return jsonify({"success": True, "history": history})
    except Exception as e:
        return jsonify({"success": False, "history": [], "message": str(e)}), 500





if __name__ == '__main__':
    print(" Tinkr API running on http://127.0.0.1:5000")
    app.run(port=5000)