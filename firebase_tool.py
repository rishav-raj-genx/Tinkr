import os
import json
from datetime import datetime, timezone

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, firestore

# --- Firebase Initialization ---
# Looks for serviceAccountKey.json in project root, or path from env var
_firebase_app = None

def _get_firestore_client():
    """Lazily initializes Firebase and returns the Firestore client."""
    global _firebase_app
    if _firebase_app is None:
        key_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_KEY", "serviceAccountKey.json")
        if not os.path.exists(key_path):
            raise FileNotFoundError(
                f"Firebase service account key not found at '{key_path}'. "
                "Download it from Firebase Console > Project Settings > Service Accounts > Generate New Private Key, "
                "and place it in the project root as 'serviceAccountKey.json'."
            )
        cred = credentials.Certificate(key_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        print("🔥 Firebase initialized successfully.")
    return firestore.client()


def save_mental_state(user_id: str, state_data: dict) -> dict:
    """
    Saves a mental state record to Firestore.
    
    Collection: users/{user_id}/mental_state_logs
    
    Args:
        user_id: Unique identifier for the user (name or email)
        state_data: Dict containing:
            - predicted_state (str): e.g. "stressed", "anxious", "calm"
            - user_confirmed (bool): Whether user confirmed the prediction
            - mean_zcr (float): Zero-crossing rate
            - rms_variance (float): RMS energy variance
            - voice_energy_level (str): "low", "medium", "high"
            - suggestions (list[str]): AI-generated suggestions
    """
    try:
        db = _get_firestore_client()
        
        doc_data = {
            "timestamp": firestore.SERVER_TIMESTAMP,
            "predicted_state": state_data.get("predicted_state", "unknown"),
            "user_confirmed": state_data.get("user_confirmed", False),
            "mean_zcr": state_data.get("mean_zcr", 0.0),
            "rms_variance": state_data.get("rms_variance", 0.0),
            "voice_energy_level": state_data.get("voice_energy_level", "medium"),
            "suggestions": state_data.get("suggestions", []),
        }
        
        doc_ref = db.collection("users").document(user_id) \
                     .collection("mental_state_logs").add(doc_data)
        
        # Also update user's latest state for quick access
        db.collection("users").document(user_id).set({
            "latest_state": state_data.get("predicted_state", "unknown"),
            "last_updated": firestore.SERVER_TIMESTAMP,
            "display_name": user_id,
        }, merge=True)
        
        print(f"✅ [FIREBASE] Saved mental state '{doc_data['predicted_state']}' for user '{user_id}'")
        return {"success": True, "message": "Mental state saved successfully."}
        
    except Exception as e:
        print(f"❌ [FIREBASE ERROR] {e}")
        return {"success": False, "message": str(e)}


def get_mental_state_history(user_id: str, limit: int = 10) -> list:
    """
    Fetches the most recent mental state logs for a user.
    
    Returns a list of dicts, newest first.
    """
    try:
        db = _get_firestore_client()
        
        docs = db.collection("users").document(user_id) \
                  .collection("mental_state_logs") \
                  .order_by("timestamp", direction=firestore.Query.DESCENDING) \
                  .limit(limit) \
                  .stream()
        
        history = []
        for doc in docs:
            data = doc.to_dict()
            # Convert Firestore timestamp to ISO string for JSON serialization
            if data.get("timestamp"):
                data["timestamp"] = data["timestamp"].isoformat()
            else:
                data["timestamp"] = "Unknown"
            history.append(data)
        
        print(f"📋 [FIREBASE] Fetched {len(history)} records for user '{user_id}'")
        return history
        
    except Exception as e:
        print(f"❌ [FIREBASE ERROR] {e}")
        return []


def get_mental_state_context(user_id: str) -> str:
    """
    Builds a context summary from recent mental state history 
    to inject into the LLM system prompt.
    
    Returns a formatted string that Gemini can use for personalized responses.
    """
    try:
        history = get_mental_state_history(user_id, limit=5)
        
        if not history:
            return "No prior mental state history available for this user."
        
        # Build context string
        lines = [f"MENTAL HEALTH CONTEXT for user '{user_id}':"]
        lines.append(f"Total recent records: {len(history)}")
        
        # Summarize patterns
        confirmed_states = [h["predicted_state"] for h in history if h.get("user_confirmed")]
        if confirmed_states:
            # Count occurrences
            state_counts = {}
            for s in confirmed_states:
                state_counts[s] = state_counts.get(s, 0) + 1
            
            most_common = max(state_counts, key=state_counts.get)
            lines.append(f"Most frequent confirmed state: {most_common} ({state_counts[most_common]} times)")
            lines.append(f"All confirmed states (recent→old): {', '.join(confirmed_states)}")
        
        # Latest entry detail
        latest = history[0]
        lines.append(f"\nLatest assessment ({latest['timestamp']}):")
        lines.append(f"  - State: {latest.get('predicted_state', 'unknown')}")
        lines.append(f"  - Confirmed: {latest.get('user_confirmed', False)}")
        lines.append(f"  - Voice Energy: {latest.get('voice_energy_level', 'unknown')}")
        
        if latest.get("suggestions"):
            lines.append(f"  - Previous suggestions given: {'; '.join(latest['suggestions'])}")
        
        lines.append("\nUse this context to provide empathetic, personalized responses. "
                     "Reference past patterns when relevant. If the user has been stressed "
                     "frequently, proactively offer calming techniques or suggest professional help.")
        
        context = "\n".join(lines)
        print(f"🧠 [FIREBASE] Built context for user '{user_id}' ({len(context)} chars)")
        return context
        
    except Exception as e:
        print(f"❌ [FIREBASE ERROR] {e}")
        return "Unable to fetch mental state history."
