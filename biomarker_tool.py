import base64
import numpy as np
import librosa

# ── Per-User Adaptive Baseline ──
# Each user gets their own baseline so multiple sessions don't collide.
# The first CALIBRATION_COUNT voice inputs establish the user's normal voice.
# After that, we only trigger when their voice deviates significantly.

CALIBRATION_COUNT = 3   # Number of samples to establish baseline
DEVIATION_FACTOR = 1.8  # How many times above baseline = anomaly
MAX_BASELINE_WINDOW = 10  # Rolling window size for baseline updates

# Per-user storage: user_id -> {"buffer": [...], "baseline": {...} or None}
_user_baselines = {}


def reset_baseline(user_id: str = None):
    """Reset calibration for a specific user or all users."""
    global _user_baselines
    if user_id:
        _user_baselines.pop(user_id, None)
    else:
        _user_baselines = {}


def _get_user_state(user_id: str) -> dict:
    """Get or initialize per-user baseline state."""
    if user_id not in _user_baselines:
        _user_baselines[user_id] = {"buffer": [], "baseline": None}
    return _user_baselines[user_id]


def _update_baseline(user_state: dict, features: dict):
    """Add a sample to calibration buffer. Compute baseline once we have enough."""
    user_state["buffer"].append(features)

    if len(user_state["buffer"]) >= CALIBRATION_COUNT and user_state["baseline"] is None:
        user_state["baseline"] = _compute_baseline(user_state["buffer"])
        print(f"✅ [BIOMARKER] Baseline calibrated after {CALIBRATION_COUNT} samples:")
        b = user_state["baseline"]
        print(f"   ZCR avg: {b['zcr']:.4f} | RMS Var avg: {b['rms_var']:.6f} | "
              f"Centroid avg: {b['centroid']:.1f} | Pitch Std avg: {b['pitch_std']:.2f}")


def _compute_baseline(buffer: list) -> dict:
    """Compute average baseline from a buffer of feature dicts."""
    return {
        "zcr": float(np.mean([f["zcr"] for f in buffer])),
        "rms_var": float(np.mean([f["rms_var"] for f in buffer])),
        "centroid": float(np.mean([f["centroid"] for f in buffer])),
        "pitch_std": float(np.mean([f["pitch_std"] for f in buffer])),
    }


def _extract_features(audio_array: np.ndarray) -> dict:
    """Extract all voice biomarker features from audio."""
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
    pitch_std = 0.0
    try:
        f0, voiced_flag, _ = librosa.pyin(
            audio_array, fmin=50, fmax=500, sr=16000
        )
        voiced_f0 = f0[voiced_flag] if voiced_flag is not None else f0[~np.isnan(f0)]
        if len(voiced_f0) > 2:
            pitch_std = float(np.std(voiced_f0))
    except Exception:
        pass

    # Voice Energy Level
    if mean_rms < 0.02:
        voice_energy_level = "low"
    elif mean_rms < 0.08:
        voice_energy_level = "medium"
    else:
        voice_energy_level = "high"

    return {
        "zcr": mean_zcr,
        "rms_var": rms_variance,
        "centroid": mean_centroid,
        "pitch_std": pitch_std,
        "mean_rms": mean_rms,
        "voice_energy_level": voice_energy_level,
    }


def _classify_state(features: dict, baseline: dict, voice_energy_level: str) -> tuple:
    """Compare features against baseline and classify emotional state.
    
    Returns:
        (predicted_state: str, alert: bool, elevated_count: int, ratios: dict)
    """
    zcr_ratio = features["zcr"] / max(baseline["zcr"], 0.001)
    rms_var_ratio = features["rms_var"] / max(baseline["rms_var"], 0.000001)
    centroid_ratio = features["centroid"] / max(baseline["centroid"], 1.0)
    pitch_ratio = features["pitch_std"] / max(baseline["pitch_std"], 0.01)

    ratios = {
        "zcr": zcr_ratio,
        "rms_var": rms_var_ratio,
        "centroid": centroid_ratio,
        "pitch": pitch_ratio,
    }

    elevated_count = sum([
        zcr_ratio > DEVIATION_FACTOR,
        rms_var_ratio > DEVIATION_FACTOR,
        centroid_ratio > DEVIATION_FACTOR,
        pitch_ratio > DEVIATION_FACTOR,
    ])

    predicted_state = "calm"
    alert = False

    # Stressed: at least 2 features significantly elevated
    if elevated_count >= 2 and (zcr_ratio > DEVIATION_FACTOR or rms_var_ratio > DEVIATION_FACTOR):
        predicted_state = "stressed"
        alert = True
    # Anxious: high pitch instability + one other elevated feature
    elif pitch_ratio > DEVIATION_FACTOR and elevated_count >= 1:
        predicted_state = "anxious"
        alert = True
    # Fatigued: very low energy, flat voice
    elif voice_energy_level == "low" and features["zcr"] < (baseline["zcr"] * 0.5):
        predicted_state = "fatigued"
        alert = True

    return predicted_state, alert, elevated_count, ratios


# ── Suggestions based on state ──
SUGGESTIONS_MAP = {
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


def _make_calm_result(voice_energy_level="medium", mean_zcr=0.0, rms_variance=0.0, message=""):
    """Build a standard calm/no-alert response dict."""
    return {
        "alert": False,
        "predicted_state": "calm",
        "voice_energy_level": voice_energy_level,
        "mean_zcr": mean_zcr,
        "rms_variance": rms_variance,
        "message": message,
        "suggestions": []
    }


def analyze_audio_biomarkers(base64_audio: str, user_id: str = "default") -> dict:
    """
    Analyzes audio biomarkers from PCM audio data using per-user adaptive baseline calibration.
    
    Phase 1 (Calibration): First 3 voice inputs establish the user's normal voice baseline.
    Phase 2 (Detection): Subsequent inputs are compared against the baseline.
                          Only triggers when features deviate significantly (1.8x above average).
    
    Args:
        base64_audio: Base64-encoded Int16 PCM audio at 16kHz
        user_id: User identifier for per-user baseline tracking
    
    Returns:
        dict with keys: alert, predicted_state, voice_energy_level, mean_zcr,
                        rms_variance, message, suggestions
    """
    try:
        # Decode base64 to binary PCM
        audio_data = base64.b64decode(base64_audio)
        audio_array_int16 = np.frombuffer(audio_data, dtype=np.int16)
        audio_array = audio_array_int16.astype(np.float32) / 32768.0

        if len(audio_array) == 0:
            return _make_calm_result(
                voice_energy_level="unknown",
                message="No audio data."
            )

        # Minimum duration: 1 second at 16kHz = 16000 samples
        if len(audio_array) < 16000:
            print(f"⏩ [BIOMARKER] Audio too short ({len(audio_array)} samples), skipping.")
            return _make_calm_result(message="Audio too short for analysis.")

        # ── Extract Features ──
        features = _extract_features(audio_array)
        voice_energy_level = features["voice_energy_level"]
        mean_zcr = features["zcr"]
        rms_variance = features["rms_var"]

        # Get per-user state
        user_state = _get_user_state(user_id)
        baseline = user_state["baseline"]

        cal_count = len(user_state["buffer"]) + 1
        baseline_status = "SET" if baseline else f"CALIBRATING ({cal_count}/{CALIBRATION_COUNT})"
        print(f"🎙️ [BIOMARKER] [{user_id}] ZCR: {mean_zcr:.4f} | RMS Var: {rms_variance:.6f} | "
              f"RMS Mean: {features['mean_rms']:.4f} | Centroid: {features['centroid']:.1f} | "
              f"Pitch Std: {features['pitch_std']:.2f} | Baseline: {baseline_status}")

        # ── Phase 1: Calibration ──
        if baseline is None:
            _update_baseline(user_state, {
                "zcr": mean_zcr,
                "rms_var": rms_variance,
                "centroid": features["centroid"],
                "pitch_std": features["pitch_std"],
            })
            return _make_calm_result(
                voice_energy_level=voice_energy_level,
                mean_zcr=mean_zcr,
                rms_variance=rms_variance,
                message="Calibrating voice baseline..."
            )

        # ── Phase 2: Deviation Detection ──
        feature_dict = {
            "zcr": mean_zcr,
            "rms_var": rms_variance,
            "centroid": features["centroid"],
            "pitch_std": features["pitch_std"],
        }
        predicted_state, alert, elevated_count, ratios = _classify_state(
            feature_dict, baseline, voice_energy_level
        )

        print(f"📊 [BIOMARKER] [{user_id}] Ratios → ZCR: {ratios['zcr']:.2f}x | "
              f"RMS Var: {ratios['rms_var']:.2f}x | Centroid: {ratios['centroid']:.2f}x | "
              f"Pitch: {ratios['pitch']:.2f}x | Elevated: {elevated_count}/4")

        # ── Continuously update baseline with calm readings ──
        if not alert:
            user_state["buffer"].append(feature_dict)
            if len(user_state["buffer"]) > MAX_BASELINE_WINDOW:
                user_state["buffer"] = user_state["buffer"][-MAX_BASELINE_WINDOW:]
            user_state["baseline"] = _compute_baseline(user_state["buffer"])

        suggestions = SUGGESTIONS_MAP.get(predicted_state, [])

        # ── Build message for LLM ──
        if alert:
            print(f"🚨 [HEALTH ALERT] [{user_id}] Detected: {predicted_state.upper()} "
                  f"(elevated {elevated_count}/4 features above {DEVIATION_FACTOR}x baseline)")
            message = (
                f"[SYSTEM EVENT: Voice biomarker analysis detected {predicted_state}. "
                f"Voice energy is {voice_energy_level}. {elevated_count} out of 4 vocal "
                f"features deviated significantly from the user's baseline. "
                f"ZCR ratio: {ratios['zcr']:.1f}x, RMS variance ratio: {ratios['rms_var']:.1f}x, "
                f"Pitch instability ratio: {ratios['pitch']:.1f}x.]"
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
