import logging
import sys

from config import config


class SecretRedactionFilter(logging.Filter):
    """Logging filter that redacts configured API keys and secrets from log messages."""

    REDACTION_STRING: str = "[REDACTED]"

    def __init__(self, name: str = "") -> None:
        super().__init__(name)

    def _redact_text(self, text: str) -> str:
        sensitive_values = config.get_sensitive_values()
        for secret in sensitive_values:
            if secret in text:
                text = text.replace(secret, self.REDACTION_STRING)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact_text(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (self._redact_text(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(
                    self._redact_text(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Configures root and Tinkr loggers with secret redaction."""
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(SecretRedactionFilter())

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        root_logger.setLevel(level)
        root_logger.addHandler(handler)


def get_logger(name: str = "tinkr") -> logging.Logger:
    """Retrieves or configures a logger for a specific module."""
    setup_logging()
    return logging.getLogger(name)


logger = get_logger("tinkr")
