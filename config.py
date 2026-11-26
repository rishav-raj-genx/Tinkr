import os
import secrets
import tempfile
import warnings
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

# Load environment variables once from .env if present
load_dotenv(BASE_DIR / ".env")


class Config:
    """Centralized typed application settings."""

    BASE_DIR: Path = BASE_DIR
    DB_PATH: Path = Path(os.getenv("DB_PATH", str(BASE_DIR / "company_data.db"))).resolve()
    TOKEN_PATH: Path = Path(os.getenv("TOKEN_PATH", str(BASE_DIR / "token.json"))).resolve()

    PORT: int = int(os.getenv("PORT", "5000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")

    FLASK_ENV: str = os.getenv("FLASK_ENV", "development").lower()
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:8000")

    # LLM & Third-Party Provider Keys
    API_KEY: str = os.getenv("API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    WEATHER_API_KEY: str = os.getenv("WEATHER_API_KEY", "")

    # Google OAuth & Workspace Settings
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
    HOST_CALENDAR_ID: str = os.getenv("HOST_CALENDAR_ID", "primary")
    HOST_EMAIL: str = os.getenv("HOST_EMAIL", "")

    # Owner Authentication & Portfolio Demo Sandbox
    OWNER_ACCESS_KEY: str = os.getenv("OWNER_ACCESS_KEY", "")

    def __init__(self) -> None:
        raw_secret = os.getenv("SECRET_KEY")
        if self.FLASK_ENV == "production":
            if not raw_secret or raw_secret == "generate_a_secure_random_string_here":
                raise RuntimeError("SECRET_KEY must be securely configured when running in production mode.")
            self.SECRET_KEY: str = raw_secret
        else:
            if not raw_secret or raw_secret == "generate_a_secure_random_string_here":
                warnings.warn(
                    "SECRET_KEY not set or using placeholder; using ephemeral dev key.",
                    UserWarning,
                    stacklevel=2,
                )
                self.SECRET_KEY = secrets.token_hex(32)
            else:
                self.SECRET_KEY = raw_secret

        # Bootstrap token.json from GOOGLE_TOKEN_JSON env var if provided (for ephemeral hosts like Render)
        token_env = os.getenv("GOOGLE_TOKEN_JSON", "").strip()
        if token_env and not self.TOKEN_PATH.exists():
            self.save_token_json(token_env)

    def diagnostics(self) -> dict[str, bool]:
        """Returns boolean-only health and integration readiness flags.

        Never exposes key values, lengths, or substrings.
        """
        return {
            "llm_configured": bool(self.API_KEY and self.API_KEY != "dummy_key"),
            "groq_configured": bool(self.GROQ_API_KEY and self.GROQ_API_KEY != "dummy_key"),
            "weather_configured": bool(self.WEATHER_API_KEY),
            "google_oauth_configured": bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET),
            "calendar_configured": bool(self.HOST_CALENDAR_ID),
            "database_present": self.DB_PATH.exists(),
            "token_present": self.TOKEN_PATH.exists(),
            "owner_mode_configured": bool(self.OWNER_ACCESS_KEY),
        }

    def get_sensitive_values(self) -> set[str]:
        """Returns non-empty secret values for logging redaction filters."""
        raw_values = {
            self.API_KEY,
            self.GROQ_API_KEY,
            self.WEATHER_API_KEY,
            self.GOOGLE_CLIENT_SECRET,
            self.SECRET_KEY,
            self.OWNER_ACCESS_KEY,
        }
        return {val for val in raw_values if val and len(val) >= 4 and val != "dummy_key"}

    def save_token_json(self, token_json: str) -> None:
        """Persist OAuth credentials atomically with owner-only permissions."""
        self.TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_path = tempfile.mkstemp(prefix=".token-", dir=self.TOKEN_PATH.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as token_file:
                token_file.write(token_json)
            os.replace(temporary_path, self.TOKEN_PATH)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise


config = Config()
