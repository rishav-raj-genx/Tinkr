import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

# Tools
from biomarker_tool import analyze_audio_biomarkers
from calendar_tool import book_meeting, check_availability
from tasks_tool import add_task, list_tasks
from sql_tool import get_database_schema, execute_sql_query
from firebase_tool import save_mental_state, get_mental_state_history, get_mental_state_context
from web_tool import search_web

app = Flask(__name__)
CORS(app)

from dotenv import load_dotenv
load_dotenv()

# Initialize OpenAI client for Fireworks AI
client = OpenAI(
    api_key=os.environ.get("FIREWORKS_API_KEY", "dummy_key"),
    base_url="https://api.fireworks.ai/inference/v1"
)
MODEL_NAME = "accounts/fireworks/models/gemma-4-e4b" 

@app.route('/api/transcribe', methods=['POST'])
def handle_transcribe():
    """
    Receives an audio file from the frontend and transcribes it using Whisper.
    """
    if 'audio' not in request.files:
        return jsonify({"success": False, "message": "No audio file provided"}), 400
    
    audio_file = request.files['audio']
    
    # Save temporarily
    temp_path = "/tmp/temp_audio.webm"
    audio_file.save(temp_path)
    
    try:
        # We can use the Groq Whisper API for insanely fast transcription
        with open(temp_path, "rb") as file:
            transcription = client.audio.transcriptions.create(
                file=file,
                model="whisper-large-v3-turbo",
                response_format="text"
            )
        text = transcription
    except Exception as e:
        print(f"Transcription error: {e}")
        text = "Error during transcription."
        
    return jsonify({"success": True, "text": text})

@app.route('/api/chat', methods=['POST'])
def handle_chat():
    """
    The core reasoning endpoint. Receives text and history, calls Gemma 4 with tools,
    and returns the final response.
    """
    data = request.json
    user_text = data.get('text', '')
    history = data.get('history', [])
    user_id = data.get('user_id', 'user')
    emotion_context = data.get('emotion_context', '')
    
    system_prompt = f"""You are a professional, empathetic AI assistant named NovaVoice.
Your core reasoning engine is Gemma 4.
The user's name/ID is "{user_id}".
Always check availability first before booking a meeting to prevent double-booking. When booking or checking, format dates strictly to ISO 8601 offset to the user's timezone.

WELLNESS ROLE: You track the user's mental wellbeing through voice biomarker analysis.
When the user expresses an emotion, be empathetic and non-judgmental.

{emotion_context}
"""
    
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})
    
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
                        "guest_email": {"type": "string", "description": "Guest email address"}
                    },
                    "required": ["title", "date_time", "guest_email"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Searches the web for current news, weather, or information.",
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
        }
    ]

    print("\n💬 [CHAT REQUEST] Prompting Gemma 4...")
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        
        response_message = response.choices[0].message
        
        # Check if the model decided to call a tool
        if response_message.tool_calls:
            messages.append(response_message) # Append assistant's tool call request to history
            
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                print(f"🔧 [TOOL CALL] {function_name}({function_args})")
                
                function_response = "Tool executed successfully."
                
                if function_name == "check_availability":
                    function_response = str(check_availability(date_iso=function_args.get("date")))
                elif function_name == "book_meeting":
                    function_response = str(book_meeting(date_time_iso=function_args.get("date_time"), name=function_args.get("guest_email")))
                elif function_name == "search_web":
                    function_response = str(search_web(query=function_args.get("query")))
                elif function_name == "add_task":
                    function_response = str(add_task(title=function_args.get("title"), notes=function_args.get("notes", "")))
                
                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                })
            
            # Second call to get the final response based on tool output
            second_response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages
            )
            final_text = second_response.choices[0].message.content
        else:
            final_text = response_message.content
            
    except Exception as e:
        print(f"❌ [CHAT ERROR] {e}")
        final_text = "I'm having trouble connecting to my brain right now."

    print(f"✅ [CHAT RESPONSE] {final_text}")
    return jsonify({"success": True, "text": final_text})


# Keep existing endpoints just in case frontend relies on them directly
@app.route('/api/book_meeting', methods=['POST'])
def handle_booking():
    data = request.json
    result = book_meeting(date_time_iso=data.get('date_time'), name=data.get('guest_email'))
    return jsonify({"result": result})

@app.route('/api/check_availability', methods=['POST'])
def handle_availability():
    data = request.json
    result = check_availability(date_iso=data.get('date'))
    return jsonify({"result": result})

@app.route('/api/add_task', methods=['POST'])
def handle_add_task():
    data = request.json
    result = add_task(title=data.get('title'), notes=data.get('notes', ''))
    return jsonify({"result": result})

@app.route('/api/list_tasks', methods=['POST'])
def handle_list_tasks():
    result = list_tasks()
    return jsonify({"result": result})

@app.route('/api/get_schema', methods=['POST'])
def handle_get_schema():
    result = get_database_schema()
    return jsonify({"result": result})

@app.route('/api/execute_sql', methods=['POST'])
def handle_execute_sql():
    data = request.json
    result = execute_sql_query(query=data.get('query'))
    return jsonify({"result": result})

@app.route('/api/analyze_audio', methods=['POST'])
def handle_analyze_audio():
    data = request.json
    result = analyze_audio_biomarkers(base64_audio=data.get('audio_base64'))
    return jsonify(result)

@app.route('/api/save_mental_state', methods=['POST'])
def handle_save_mental_state():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"success": False, "message": "user_id is required."}), 400
    
    state_data = {
        "predicted_state": data.get("predicted_state", "unknown"),
        "user_confirmed": data.get("user_confirmed", False),
        "mean_zcr": data.get("mean_zcr", 0.0),
        "rms_variance": data.get("rms_variance", 0.0),
        "voice_energy_level": data.get("voice_energy_level", "medium"),
        "suggestions": data.get("suggestions", []),
    }
    result = save_mental_state(user_id=user_id, state_data=state_data)
    return jsonify(result)

@app.route('/api/get_mental_state_history', methods=['POST'])
def handle_get_mental_state_history():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"success": False, "history": [], "message": "user_id is required."}), 400
    
    limit = data.get("limit", 10)
    history = get_mental_state_history(user_id=user_id, limit=limit)
    return jsonify({"success": True, "history": history})

@app.route('/api/get_mental_state_context', methods=['POST'])
def handle_get_mental_state_context():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"success": False, "context": ""}), 400
    context = get_mental_state_context(user_id=user_id)
    return jsonify({"success": True, "context": context})

if __name__ == '__main__':
    print("🚀 NovaVoice API running on http://127.0.0.1:5000")
    app.run(port=5000)