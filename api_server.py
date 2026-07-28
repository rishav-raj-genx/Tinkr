import os
import json
from datetime import datetime, timezone
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
from groq import Groq

# Tools
from biomarker_tool import analyze_audio_biomarkers
from calendar_tool import book_meeting, check_availability
from tasks_tool import add_task, list_tasks
from sql_tool import get_database_schema, execute_sql_query
from web_tool import search_web, get_news
from weather_tool import get_weather

app = Flask(__name__)
CORS(app)

from dotenv import load_dotenv
load_dotenv()

# In-memory storage for Tinkr hackathon (NO Firebase)
user_mental_states = {} # user_id -> list of state_data dicts
chat_histories = {}     # user_id -> list of message dicts

# Initialize OpenAI client for Google AI Studio (Gemini)
client = OpenAI(
    api_key=os.environ.get("API_KEY", "dummy_key"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)
MODEL_NAME = "gemma-4-26b-a4b-it" 

# Initialize Groq client for Whisper STT
groq_client = Groq(
    api_key=os.environ.get("GROQ_API_KEY", "dummy_key")
)

@app.route('/api/transcribe', methods=['POST'])
def handle_transcribe():
    """
    Receives an audio file from the frontend and transcribes it using Whisper.
    """
    print("\n--- PIPELINE STEP 1: STT ---")
    if 'audio' not in request.files:
        print(" [STT ERROR] No audio file provided in request.")
        return jsonify({"success": False, "message": "No audio file provided"}), 400
    
    audio_file = request.files['audio']
    
    # Save temporarily
    temp_path = "/tmp/temp_audio.webm"
    audio_file.save(temp_path)
    
    try:
        # We can use the Groq Whisper API for insanely fast transcription
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

@app.route('/api/chat', methods=['POST'])
def handle_chat():
    """
    The core reasoning endpoint. Receives text, calls Gemma 4 with tools,
    and returns the final response. Maintains history in-memory.
    """
    print("\n--- PIPELINE STEP 3: GEMMA 4 BRAIN ---")
    data = request.json
    user_text = data.get('text', '')
    user_id = data.get('user_id', 'user')
    emotion_context = data.get('emotion_context', '')
    
    if user_id not in chat_histories:
        chat_histories[user_id] = []
        
    current_time = datetime.now().astimezone().isoformat()
        
    system_prompt = f"""You are a professional, empathetic AI assistant named Tinkr.
Your core reasoning engine is Gemma 4.
The user's name/ID is "{user_id}".
The current date and time is: {current_time}.
The user's timezone is Indian Standard Time (IST, UTC+05:30). Always use +05:30 offset in ISO 8601 dates.
Always check availability first before booking a meeting to prevent double-booking.
Do NOT use markdown formatting (like asterisks **, hashtags #, etc.). Keep the output as plain conversational text.
If the user asks for the weather without specifying a location, ask them for their city.
If any tool returns an error, you MUST explicitly tell the user what went wrong in a friendly way.

{emotion_context}
"""
    
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_histories[user_id])
    messages.append({"role": "user", "content": user_text})
    
# Global tools definition
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
                    "guest_name": {"type": "string", "description": "Name or identifier of the guest"}
                },
                "required": ["title", "date_time", "guest_name"]
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
    }
]

from flask import Response, stream_with_context

@app.route('/api/chat_stream', methods=['POST'])
def handle_chat_stream():
    """
    Ultra-low latency SSE streaming endpoint with intent-based tool bypass.
    """
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
    
    system_prompt = f"""You are Tinkr, a fast, empathetic voice assistant. Keep all spoken responses extremely concise, conversational, and under 2 sentences unless detailed information is requested.
Your core reasoning engine is Gemma 4.
The user's name/ID is "{user_id}".
The current date and time is: {current_time}.
The user's timezone is Indian Standard Time (IST, UTC+05:30). Always use +05:30 offset in ISO 8601 dates.
Always check availability first before booking a meeting to prevent double-booking.
Do NOT use markdown formatting (like asterisks **, hashtags #, etc.). Keep the output as plain conversational text.
If the user asks for the weather without specifying a location, ask them for their city.
If any tool returns an error, you MUST explicitly tell the user what went wrong in a friendly way.{wellness_instruction}"""

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_histories[user_id])
    messages.append({"role": "user", "content": user_text})
    
    # Intent-Based Tool Bypass
    text_lower = user_text.lower()
    trigger_words = ["calendar", "schedule", "book", "news", "search", "weather", "task", "todo", "meeting", "remind", "reminder", "list", "pending"]
    needs_tools = any(word in text_lower for word in trigger_words)
    
    active_tools = tools if needs_tools else None
    
    def generate():
        try:
            if active_tools:
                # Need to handle tools synchronously first because tools block streaming
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
                            if function_name == "check_availability":
                                function_response = str(check_availability(date_iso=function_args.get("date")))
                            elif function_name == "book_meeting":
                                function_response = str(book_meeting(date_time_iso=function_args.get("date_time"), name=function_args.get("guest_name", "Guest")))
                            elif function_name == "search_web":
                                function_response = str(search_web(query=function_args.get("query")))
                            elif function_name == "get_news":
                                function_response = str(get_news(query=function_args.get("query")))
                            elif function_name == "get_weather":
                                function_response = str(get_weather(location=function_args.get("location")))
                            elif function_name == "add_task":
                                function_response = str(add_task(title=function_args.get("title"), notes=function_args.get("notes", "")))
                            else:
                                function_response = "Unknown tool."
                        except Exception as ex:
                            function_response = f"Error executing tool: {ex}"
                        
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": function_response,
                        })
            
            # Now stream the final response (or the only response if no tools used)
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
                        # Advanced thought tag stripping logic for stream
                        thought_buffer += delta
                        
                        while thought_buffer:
                            if in_thought:
                                end_thought = thought_buffer.find("</thought>")
                                end_think = thought_buffer.find("</think>")
                                end_idx = max(end_thought, end_think)
                                if end_idx != -1:
                                    # Found the end tag
                                    in_thought = False
                                    tag_len = 10 if end_thought != -1 else 8
                                    thought_buffer = thought_buffer[end_idx + tag_len:]
                                else:
                                    # Still in thought, consume buffer completely
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
                                    # Found start tag
                                    safe_text = thought_buffer[:start_idx]
                                    if safe_text:
                                        full_text += safe_text
                                        yield f"data: {json.dumps({'text': safe_text})}\n\n"
                                    thought_buffer = thought_buffer[start_idx:]
                                    in_thought = True
                                else:
                                    # No start tag. If buffer has '<', wait. Else yield.
                                    if '<' in thought_buffer:
                                        break # Wait for more chunks to resolve potential tag
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
            import traceback
            traceback.print_exc()
            print(f" [CHAT STREAM ERROR] {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

    print(f" [CHAT REQUEST] Prompting {MODEL_NAME} for user '{user_id}'...")
    
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
                
                try:
                    function_args = json.loads(tool_call.function.arguments)
                    print(f" [TOOL CALL] {function_name}({function_args})")
                    
                    if function_name == "check_availability":
                        print("--- PIPELINE STEP 4: GOOGLE CALENDAR TOOL ---")
                        function_response = str(check_availability(date_iso=function_args.get("date")))
                        print(f" [CALENDAR SUCCESS] {function_response}")
                    elif function_name == "book_meeting":
                        print("--- PIPELINE STEP 4: GOOGLE CALENDAR TOOL ---")
                        function_response = str(book_meeting(date_time_iso=function_args.get("date_time"), name=function_args.get("guest_email")))
                        print(f" [CALENDAR SUCCESS] {function_response}")
                    elif function_name == "search_web":
                        print("--- PIPELINE STEP 5: WEB SEARCH TOOL ---")
                        function_response = str(search_web(query=function_args.get("query")))
                        print(f" [SEARCH SUCCESS] Retrieved {len(function_response)} chars.")
                    elif function_name == "get_news":
                        print("--- PIPELINE STEP 5: NEWS TOOL ---")
                        function_response = str(get_news(query=function_args.get("query")))
                        print(f" [NEWS SUCCESS] Retrieved {len(function_response)} chars.")
                    elif function_name == "get_weather":
                        print("--- PIPELINE STEP 5: WEATHER TOOL ---")
                        function_response = str(get_weather(location=function_args.get("location")))
                        print(f" [WEATHER SUCCESS] Retrieved {len(function_response)} chars.")
                    elif function_name == "add_task":
                        function_response = str(add_task(title=function_args.get("title"), notes=function_args.get("notes", "")))
                    else:
                        function_response = "Unknown tool."
                except Exception as ex:
                    print(f" [TOOL ERROR] Failed to execute {function_name}: {ex}")
                    function_response = f"Error executing tool: {ex}"
                
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
            
        print(f" [CHAT SUCCESS] Final response generated.")
        
        # Strip <thought> and <think> tags (and their contents) from final_text so TTS doesn't read them
        import re
        final_text = re.sub(r'<thought>.*?</thought>', '', final_text, flags=re.DOTALL)
        final_text = re.sub(r'<think>.*?</think>', '', final_text, flags=re.DOTALL)
        final_text = final_text.strip()
        
        # Update history
        chat_histories[user_id].append({"role": "user", "content": user_text})
        chat_histories[user_id].append({"role": "assistant", "content": final_text})
        
    except Exception as e:
        print(f" [CHAT ERROR] {e}")
        final_text = "I'm having trouble connecting to my brain right now."

    print(f" [CHAT RESPONSE] {final_text}")
    print("--- PIPELINE STEP 6: TTS --- (Sent to frontend for Web Speech API playback)")
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
    print("\n--- PIPELINE STEP 2: EMOTION TRACKING ---")
    data = request.json
    try:
        result = analyze_audio_biomarkers(base64_audio=data.get('audio_base64'))
        print(f" [EMOTION SUCCESS] Biomarkers analyzed. Alert: {result.get('alert')}")
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
    
    state_data = {
        "predicted_state": data.get("predicted_state", "unknown"),
        "user_confirmed": data.get("user_confirmed", False),
        "mean_zcr": data.get("mean_zcr", 0.0),
        "rms_variance": data.get("rms_variance", 0.0),
        "voice_energy_level": data.get("voice_energy_level", "medium"),
        "suggestions": data.get("suggestions", []),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if user_id not in user_mental_states:
        user_mental_states[user_id] = []
    
    user_mental_states[user_id].insert(0, state_data) # Add to front (newest first)
    
    print(f" [IN-MEMORY STATE] Saved mental state for '{user_id}': {state_data['predicted_state']}")
    return jsonify({"success": True, "message": "Mental state saved successfully."})

@app.route('/api/get_mental_state_history', methods=['POST'])
def handle_get_mental_state_history():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"success": False, "history": [], "message": "user_id is required."}), 400
    
    limit = data.get("limit", 10)
    history = user_mental_states.get(user_id, [])[:limit]
    
    return jsonify({"success": True, "history": history})

@app.route('/api/get_mental_state_context', methods=['POST'])
def handle_get_mental_state_context():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({"success": False, "context": ""}), 400
    
    history = user_mental_states.get(user_id, [])[:5]
    
    if not history:
        return jsonify({"success": True, "context": "No prior mental state history available for this user."})
        
    lines = [f"MENTAL HEALTH CONTEXT for user '{user_id}':"]
    lines.append(f"Total recent records: {len(history)}")
    
    confirmed_states = [h["predicted_state"] for h in history if h.get("user_confirmed")]
    if confirmed_states:
        state_counts = {}
        for s in confirmed_states:
            state_counts[s] = state_counts.get(s, 0) + 1
        most_common = max(state_counts, key=state_counts.get)
        lines.append(f"Most frequent confirmed state: {most_common} ({state_counts[most_common]} times)")
    
    latest = history[0]
    lines.append(f"\nLatest assessment ({latest['timestamp']}):")
    lines.append(f"  - State: {latest.get('predicted_state', 'unknown')}")
    lines.append(f"  - Confirmed: {latest.get('user_confirmed', False)}")
    lines.append(f"  - Voice Energy: {latest.get('voice_energy_level', 'unknown')}")
    
    context = "\n".join(lines)
    return jsonify({"success": True, "context": context})

if __name__ == '__main__':
    print(" Tinkr API running on http://127.0.0.1:5000")
    app.run(port=5000)