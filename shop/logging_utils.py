import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Serialize log records as one-line JSON objects."""

    _reserved = {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }

    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        record_payload = getattr(record, "payload", None)
        if isinstance(record_payload, dict):
            payload["payload"] = record_payload

        for key, value in record.__dict__.items():
            if key in self._reserved or key == "payload" or key.startswith("_"):
                continue
            payload[key] = self._safe_value(value)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=True)

    @staticmethod
    def _safe_value(value):
        try:
            json.dumps(value)
            return value
        except TypeError:
            return str(value)
