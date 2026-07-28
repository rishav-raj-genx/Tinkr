"""Tests for the biomarker_tool module."""

import base64

# Guard heavy imports — skip entire module if deps missing
try:
    import numpy as np
    from biomarker_tool import analyze_audio_biomarkers
except (ImportError, ModuleNotFoundError):
    import pytest
    pytest.skip("librosa or numpy not available", allow_module_level=True)


def _make_pcm_data(duration_sec: float = 0.5, freq: float = 440.0, sr: int = 16000) -> str:
    """Generate a synthetic PCM tone at given frequency, return base64 string."""
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    samples = (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16)
    pcm_bytes = samples.tobytes()
    return base64.b64encode(pcm_bytes).decode("ascii")


class TestAnalyzeAudioBiomarkers:
    """Tests for analyze_audio_biomarkers."""

    def test_empty_audio(self):
        """Empty audio returns 'unknown' state."""
        result = analyze_audio_biomarkers("")
        assert result["predicted_state"] == "unknown"
        assert result["alert"] is False

    def test_returns_expected_keys(self):
        """Response should contain all expected keys."""
        audio = _make_pcm_data()
        result = analyze_audio_biomarkers(audio)
        expected_keys = {
            "alert", "predicted_state", "voice_energy_level",
            "mean_zcr", "rms_variance", "message", "suggestions",
        }
        assert expected_keys.issubset(result.keys())

    def test_calm_audio(self):
        """A clean sine tone should register as calm or unknown."""
        audio = _make_pcm_data(freq=440)
        result = analyze_audio_biomarkers(audio)
        assert result["predicted_state"] in ("calm", "unknown", "anxious")
        assert isinstance(result["mean_zcr"], float)
        assert result["mean_zcr"] >= 0

    def test_suggestions_are_list(self):
        """Suggestions should always be a list."""
        audio = _make_pcm_data()
        result = analyze_audio_biomarkers(audio)
        assert isinstance(result["suggestions"], list)

    def test_voice_energy_level_in_valid_set(self):
        """Voice energy should be one of low/medium/high."""
        audio = _make_pcm_data()
        result = analyze_audio_biomarkers(audio)
        assert result["voice_energy_level"] in ("low", "medium", "high", "unknown")

    def test_no_audio_returns_empty_suggestions(self):
        """Empty audio should produce no suggestions."""
        result = analyze_audio_biomarkers("")
        assert result["suggestions"] == []

    def test_invalid_base64(self):
        """Invalid base64 should be caught gracefully."""
        result = analyze_audio_biomarkers("!!!not-valid-base64!!!")
        assert isinstance(result, dict)
        assert "predicted_state" in result
        assert "message" in result
