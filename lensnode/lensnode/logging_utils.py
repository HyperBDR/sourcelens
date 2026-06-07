from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit, urlunsplit


def utc_now():
    """Return the current UTC datetime."""

    return datetime.now(timezone.utc)


def format_utc(value=None):
    """Format a UTC timestamp for task detail logs."""

    current = value or utc_now()
    return current.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def format_duration(seconds):
    """Format seconds as a compact human-readable duration."""

    remaining = max(0, int(seconds))
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, seconds = divmod(remaining, 60)

    parts = []
    if days:
        parts.append(f"{days} days")
    if hours:
        parts.append(f"{hours} hours")
    if minutes:
        parts.append(f"{minutes} mins")
    if seconds or not parts:
        parts.append(f"{seconds} secs")
    return " ".join(parts)


def task_log(message, timestamp=None, details=None):
    """Build a normalized task detail log message."""

    output = f"[{format_utc(timestamp)}] - {message}"
    if details:
        output = "\n".join([output, *details])
    return output


def elapsed_since(started_at):
    """Return formatted elapsed time since a UTC start timestamp."""

    return format_duration((utc_now() - started_at).total_seconds())


def safe_ws_url(url):
    """Return a WebSocket URL with token-like query values redacted."""

    parts = urlsplit(url)
    safe_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if "token" in key.lower():
            safe_query.append((key, "***"))
        else:
            safe_query.append((key, value))
    query = "&".join(f"{key}={value}" for key, value in safe_query)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            query,
            parts.fragment,
        )
    )
