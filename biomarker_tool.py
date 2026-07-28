import base64
import numpy as np
import librosa

# ── Per-Session Adaptive Baseline ──
# Instead of fixed thresholds (which fail with browser mic noise), we learn
# what the user's NORMAL voice sounds like over the first few interactions,
# then only trigger when their voice significantly deviates from their baseline.

_baseline_buffer = []  # Stores feature dicts from calibration phase
_baseline = None       # Computed baseline averages once calibration is done
CALIBRATION_COUNT = 3  # Number of samples needed to establish baseline
DEVIATION_FACTOR = 1.8 # How many times above baseline = anomaly

def _reset_baseline():
    """Reset calibration (e.g., on new session)."""
    global _baseline_buffer, _baseline
    _baseline_buffer = []
    _baseline = None

def _update_baseline(features: dict):
    """Add a sample to calibration buffer. Once we have enough, compute baseline."""
    global _baseline_buffer, _baseline
    _baseline_buffer.append(features)
    
    if len(_baseline_buffer) >= CALIBRATION_COUNT:
        _baseline = {
            "zcr": np.mean([f["zcr"] for f in _baseline_buffer]),
            "rms_var": np.mean([f["rms_var"] for f in _baseline_buffer]),
            "centroid": np.mean([f["centroid"] for f in _baseline_buffer]),
            "pitch_std": np.mean([f["pitch_std"] for f in _baseline_buffer]),
        }
        print(f"✅ [BIOMARKER] Baseline calibrated after {CALIBRATION_COUNT} samples:")
        print(f"   ZCR avg: {_baseline['zcr']:.4f} | RMS Var avg: {_baseline['rms_var']:.6f} | "
              f"Centroid avg: {_baseline['centroid']:.1f} | Pitch Std avg: {_baseline['pitch_std']:.2f}")


def analyze_audio_biomarkers(base64_audio: str) -> dict:
    """
    Analyzes audio biomarkers from PCM audio data using adaptive baseline calibration.
    
    Phase 1 (Calibration): First 3 voice inputs establish the user's normal voice baseline.
    Phase 2 (Detection): Subsequent inputs are compared against the baseline.
                          Only triggers when features deviate significantly (1.8x above average).
    
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
    global _baseline, _baseline_buffer
    
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
        
        # Minimum duration: 1 second at 16kHz = 16000 samples
        if len(audio_array) < 16000:
            print(f"⏩ [BIOMARKER] Audio too short ({len(audio_array)} samples), skipping.")
            return {
                "alert": False,
                "predicted_state": "calm",
                "voice_energy_level": "medium",
                "mean_zcr": 0.0,
                "rms_variance": 0.0,
                "message": "Audio too short for analysis.",
                "suggestions": []
            }
            
        # ── Feature Extraction ──
        
        # 1. Zero Crossing Rate
        zcr = librosa.feature.zero_crossing_rate(y=audio_array)
        mean_zcr = float(np.mean(zcr))
        
        # 2. RMS Energy
        rms = librosa.feature.rms(y=audio_array)
        mean_rms = float(np.mean(rms))
        rms_variance = float(np.var(rms))
        
        # 3. Spectral Centroid
        spectral_centroid = librosa.feature.spectral_centroid(y=audio_array, sr=16000)
        mean_centroid = float(np.mean(spectral_centroid))
        
        # 4. Pitch (F0) Stability — jittery pitch = stress indicator
        try:
            f0, voiced_flag, _ = librosa.pyin(
                audio_array, fmin=50, fmax=500, sr=16000
            )
            # Only consider voiced frames
            voiced_f0 = f0[voiced_flag] if voiced_flag is not None else f0[~np.isnan(f0)]
            if len(voiced_f0) > 2:
                pitch_std = float(np.std(voiced_f0))
            else:
                pitch_std = 0.0
        except Exception:
            pitch_std = 0.0
        
        # ── Voice Energy Level ──
        if mean_rms < 0.02:
            voice_energy_level = "low"
        elif mean_rms < 0.08:
            voice_energy_level = "medium"
        else:
            voice_energy_level = "high"
        
        features = {
            "zcr": mean_zcr,
            "rms_var": rms_variance,
            "centroid": mean_centroid,
            "pitch_std": pitch_std,
        }
        
        print(f"🎙️ [BIOMARKER] ZCR: {mean_zcr:.4f} | RMS Var: {rms_variance:.6f} | "
              f"RMS Mean: {mean_rms:.4f} | Centroid: {mean_centroid:.1f} | "
              f"Pitch Std: {pitch_std:.2f} | Baseline: {'SET' if _baseline else f'CALIBRATING ({len(_baseline_buffer)+1}/{CALIBRATION_COUNT})'}")
        
        # ── Phase 1: Calibration ──
        if _baseline is None:
            _update_baseline(features)
            return {
                "alert": False,
                "predicted_state": "calm",
                "voice_energy_level": voice_energy_level,
                "mean_zcr": mean_zcr,
                "rms_variance": rms_variance,
                "message": "Calibrating voice baseline...",
                "suggestions": []
            }
        
        # ── Phase 2: Deviation Detection ──
        zcr_ratio = mean_zcr / max(_baseline["zcr"], 0.001)
        rms_var_ratio = rms_variance / max(_baseline["rms_var"], 0.000001)
        centroid_ratio = mean_centroid / max(_baseline["centroid"], 1.0)
        pitch_ratio = pitch_std / max(_baseline["pitch_std"], 0.01)
        
        # Count how many features are elevated above the deviation threshold
        elevated_count = sum([
            zcr_ratio > DEVIATION_FACTOR,
            rms_var_ratio > DEVIATION_FACTOR,
            centroid_ratio > DEVIATION_FACTOR,
            pitch_ratio > DEVIATION_FACTOR,
        ])
        
        print(f"📊 [BIOMARKER] Ratios → ZCR: {zcr_ratio:.2f}x | RMS Var: {rms_var_ratio:.2f}x | "
              f"Centroid: {centroid_ratio:.2f}x | Pitch: {pitch_ratio:.2f}x | "
              f"Elevated: {elevated_count}/4")
        
        predicted_state = "calm"
        alert = False
        
        # Stressed: at least 2 features must be significantly elevated
        if elevated_count >= 2 and (zcr_ratio > DEVIATION_FACTOR or rms_var_ratio > DEVIATION_FACTOR):
            predicted_state = "stressed"
            alert = True
        # Anxious: high pitch instability + one other elevated feature
        elif pitch_ratio > DEVIATION_FACTOR and elevated_count >= 1:
            predicted_state = "anxious"
            alert = True
        # Fatigued: very low energy, flat voice
        elif voice_energy_level == "low" and mean_zcr < (_baseline["zcr"] * 0.5):
            predicted_state = "fatigued"
            alert = True
        
        # ── Continuously update baseline with calm readings ──
        # This lets the baseline adapt over time as the session progresses
        if not alert:
            _baseline_buffer.append(features)
            # Keep a rolling window of the last 10 readings
            if len(_baseline_buffer) > 10:
                _baseline_buffer = _baseline_buffer[-10:]
            _baseline = {
                "zcr": np.mean([f["zcr"] for f in _baseline_buffer]),
                "rms_var": np.mean([f["rms_var"] for f in _baseline_buffer]),
                "centroid": np.mean([f["centroid"] for f in _baseline_buffer]),
                "pitch_std": np.mean([f["pitch_std"] for f in _baseline_buffer]),
            }
        
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
            print(f"🚨 [HEALTH ALERT] Detected mental state: {predicted_state.upper()} "
                  f"(elevated {elevated_count}/4 features above {DEVIATION_FACTOR}x baseline)")
            message = (
                f"[SYSTEM EVENT: Voice biomarker analysis detected {predicted_state}. "
                f"Voice energy is {voice_energy_level}. {elevated_count} out of 4 vocal "
                f"features deviated significantly from the user's baseline. "
                f"ZCR ratio: {zcr_ratio:.1f}x, RMS variance ratio: {rms_var_ratio:.1f}x, "
                f"Pitch instability ratio: {pitch_ratio:.1f}x.]"
            )
        else:
            message = "Vocal markers within normal baseline range. User appears calm."
        
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
