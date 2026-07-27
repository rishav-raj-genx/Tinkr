import base64
import numpy as np
import librosa

def analyze_audio_biomarkers(base64_audio: str) -> dict:
    """
    Analyzes audio biomarkers from PCM audio data and returns a rich mental state prediction.
    
    Returns:
        dict with keys:
            - alert (bool): Whether an anomaly was detected
            - predicted_state (str): "stressed", "anxious", "fatigued", "calm"
            - voice_energy_level (str): "low", "medium", "high"
            - mean_zcr (float): Zero-crossing rate
            - rms_variance (float): RMS energy variance
            - message (str): System message for LLM injection
            - suggestions (list[str]): Wellbeing suggestions based on detected state
    """
    try:
        # Decode base64 to binary PCM
        audio_data = base64.b64decode(base64_audio)
        
        # The frontend sends 16kHz Int16 PCM data
        audio_array_int16 = np.frombuffer(audio_data, dtype=np.int16)
        
        # Convert to float32 and normalize for librosa
        audio_array = audio_array_int16.astype(np.float32) / 32768.0
        
        if len(audio_array) == 0:
            return {
                "alert": False,
                "predicted_state": "unknown",
                "voice_energy_level": "unknown",
                "mean_zcr": 0.0,
                "rms_variance": 0.0,
                "message": "No audio data.",
                "suggestions": []
            }
            
        # ── Feature Extraction using Librosa ──
        
        # 1. Zero Crossing Rate (Proxy for vocal breathiness or raspiness)
        zcr = librosa.feature.zero_crossing_rate(y=audio_array)
        mean_zcr = float(np.mean(zcr))
        
        # 2. RMS Energy (Proxy for shimmer / amplitude micro-tremors)
        rms = librosa.feature.rms(y=audio_array)
        mean_rms = float(np.mean(rms))
        rms_variance = float(np.var(rms))
        
        # 3. Spectral Centroid (brightness of voice — higher when tense)
        spectral_centroid = librosa.feature.spectral_centroid(y=audio_array, sr=16000)
        mean_centroid = float(np.mean(spectral_centroid))
        
        print(f"🎙️ [BIOMARKER] ZCR: {mean_zcr:.4f} | RMS Var: {rms_variance:.6f} | "
              f"RMS Mean: {mean_rms:.4f} | Centroid: {mean_centroid:.1f}")
        
        # ── Voice Energy Level ──
        if mean_rms < 0.02:
            voice_energy_level = "low"
        elif mean_rms < 0.08:
            voice_energy_level = "medium"
        else:
            voice_energy_level = "high"
        
        # ── Mental State Prediction ──
        # Based on combination of vocal features
        predicted_state = "calm"
        alert = False
        
        if mean_zcr > 0.08 and rms_variance > 0.0002:
            predicted_state = "stressed"
            alert = True
        elif mean_zcr > 0.06 and mean_centroid > 2500:
            predicted_state = "anxious"
            alert = True
        elif mean_zcr > 0.05 or rms_variance > 0.0001:
            predicted_state = "stressed"
            alert = True
        elif voice_energy_level == "low" and mean_zcr < 0.03:
            predicted_state = "fatigued"
            alert = True
        
        # ── Suggestions based on state ──
        suggestions_map = {
            "stressed": [
                "Try deep breathing: inhale 4 seconds, hold 4, exhale 6",
                "Take a 5-minute break and stretch",
                "Consider a short mindfulness meditation",
                "Drink some water and step away from your screen"
            ],
            "anxious": [
                "Practice grounding: name 5 things you can see, 4 you can touch",
                "Try progressive muscle relaxation",
                "Write down what's on your mind to externalize worries",
                "Listen to calming music for a few minutes"
            ],
            "fatigued": [
                "Consider taking a power nap (15-20 minutes)",
                "Get some fresh air and sunlight",
                "Have a healthy snack for an energy boost",
                "Do some light stretching to increase blood flow"
            ],
            "calm": [
                "Great state of mind! Keep up the good work",
                "This is a good time for focused, creative work"
            ]
        }
        
        suggestions = suggestions_map.get(predicted_state, [])
        
        # ── Build message for LLM ──
        if alert:
            print(f"🚨 [HEALTH ALERT] Detected mental state: {predicted_state.upper()}")
            message = (
                f"[SYSTEM EVENT: Biomarker analysis complete. Voice analysis indicates the user "
                f"may be feeling {predicted_state}. Voice energy is {voice_energy_level}. "
                f"Zero-crossing rate: {mean_zcr:.4f}, RMS variance: {rms_variance:.6f}. "
                f"Ask the user to confirm if they are feeling {predicted_state}, and offer "
                f"supportive suggestions. Be empathetic and natural.]"
            )
        else:
            message = "Vocal markers normal. User appears calm."
        
        return {
            "alert": alert,
            "predicted_state": predicted_state,
            "voice_energy_level": voice_energy_level,
            "mean_zcr": mean_zcr,
            "rms_variance": rms_variance,
            "message": message,
            "suggestions": suggestions
        }
            
    except Exception as e:
        print(f"❌ Audio Processing Error: {e}")
        return {
            "alert": False,
            "predicted_state": "unknown",
            "voice_energy_level": "unknown",
            "mean_zcr": 0.0,
            "rms_variance": 0.0,
            "message": str(e),
            "suggestions": []
        }
