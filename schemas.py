import base64
import binascii
from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictBaseModel(BaseModel):
    """Base schema forbidding extra fields and stripping whitespace."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PredictedState(str, Enum):
    CALM = "calm"
    STRESSED = "stressed"
    ANXIOUS = "anxious"
    FATIGUED = "fatigued"


class ChatStreamRequest(StrictBaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    user_id: Optional[str] = Field(default="user", max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    emotion_context: str = Field(default="", max_length=500)

    @field_validator("user_id", mode="before")
    @classmethod
    def set_default_user_id(cls, v: Any) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            return "user"
        return v

    @field_validator("emotion_context", mode="before")
    @classmethod
    def normalize_emotion_context(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


class AnalyzeAudioRequest(StrictBaseModel):
    audio_base64: str = Field(..., min_length=16, max_length=2_800_000)
    user_id: Optional[str] = Field(default="default", max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")

    @field_validator("user_id", mode="before")
    @classmethod
    def set_default_user_id(cls, v: Any) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            return "default"
        return v

    @field_validator("audio_base64")
    @classmethod
    def validate_audio_base64(cls, v: str) -> str:
        try:
            decoded = base64.b64decode(v, validate=True)
        except (binascii.Error, ValueError) as err:
            raise ValueError(f"Invalid base64 payload: {err}") from err
        if len(decoded) % 2 != 0:
            raise ValueError("Decoded audio bytes must have an even length (int16 PCM)")
        return v


class SaveMentalStateRequest(StrictBaseModel):
    user_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    predicted_state: PredictedState
    user_confirmed: bool = False
    mean_zcr: float = Field(default=0.0, ge=0.0)
    rms_variance: float = Field(default=0.0, ge=0.0)
    voice_energy_level: str = Field(default="medium", max_length=32)
    suggestions: List[str] = Field(default_factory=list, max_length=50)
    message: Optional[str] = Field(default=None, max_length=2000)
    notes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("predicted_state", mode="before")
    @classmethod
    def normalize_state(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower().strip()
        return v


class SaveEmotionalChatRequest(StrictBaseModel):
    user_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    emotional_state_id: int = Field(..., ge=1)
    user_message: str = Field(default="", max_length=2000)
    assistant_message: str = Field(default="", max_length=2000)
    message: Optional[str] = Field(default=None, max_length=2000)
    notes: Optional[str] = Field(default=None, max_length=2000)
    predicted_state: Optional[PredictedState] = None

    @field_validator("predicted_state", mode="before")
    @classmethod
    def normalize_state(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.lower().strip()
        return v


class HistoryQueryRequest(StrictBaseModel):
    user_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    limit: Optional[int] = Field(default=20, ge=1, le=50)

    @field_validator("limit", mode="before")
    @classmethod
    def set_default_limit(cls, v: Any) -> int:
        if v is None:
            return 20
        return v


class GetEmotionalChatsRequest(StrictBaseModel):
    emotional_state_id: int = Field(..., ge=1)


class OwnerAuthRequest(StrictBaseModel):
    access_key: str = Field(..., min_length=1, max_length=256)
