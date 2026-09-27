"""Safe, structured application logging helpers."""

import logging
import re


_SENSITIVE_PATTERN = re.compile(
    r"(?i)([\"']?(?:password|secret|token|access[_ -]?key|client[_ -]?secret|"
    r"authorization|credential|subscription[_ -]?id|tenant[_ -]?id|client[_ -]?id)[\"']?"
    r"\s*[:=]\s*)(?:[\"']?)([^\s,;}\]]+)"
)


class RedactingFilter(logging.Filter):
    def filter(self, record):
        record.msg = _SENSITIVE_PATTERN.sub(r"\1[REDACTED]", record.getMessage())
        record.args = ()
        return True


class RedactingFormatter(logging.Formatter):
    """Redact sensitive key/value pairs from messages and tracebacks alike."""

    def format(self, record):
        return _SENSITIVE_PATTERN.sub(r"\1[REDACTED]", super().format(record))


def configure_logging(app):
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter(
        "%(asctime)s %(levelname)s %(name)s event=%(message)s"
    ))
    handler.addFilter(RedactingFilter())
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False


def log_event(logger, event, **fields):
    """Log only allow-listed operational metadata, never request bodies."""
    safe_fields = {
        key: value for key, value in fields.items()
        if key in {"user_id", "migration_id", "operation", "status", "category"}
    }
    details = " ".join(f"{key}={value}" for key, value in safe_fields.items())
    logger.info("%s %s", event, details)
