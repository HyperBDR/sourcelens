"""
In-memory log collector for task execution logs.
Public API: import from agentcore_task.adapters.django.
"""
import time
from typing import Dict, List, Optional


class TaskLogCollector:
    """Stores log messages in memory for task runs."""

    def __init__(self, max_records: int = 1000):
        self.records: List[Dict] = []
        self.max_records = max_records

    def _add_log(
        self,
        level: str,
        message: str,
        exception: Optional[str] = None,
    ):
        if len(self.records) >= self.max_records:
            self.records.pop(0)
        log_entry = {
            "level": level,
            "message": message,
            "timestamp": time.time(),
        }
        if exception:
            log_entry["exception"] = exception
        self.records.append(log_entry)

    def info(self, message: str):
        """Append an INFO-level log entry."""
        self._add_log("INFO", message)

    def warning(self, message: str):
        """Append a WARNING-level log entry."""
        self._add_log("WARNING", message)

    def error(self, message: str, exception: Optional[str] = None):
        """Append an ERROR-level log entry, optionally with exception text."""
        self._add_log("ERROR", message, exception)

    def debug(self, message: str):
        """Append a DEBUG-level log entry."""
        self._add_log("DEBUG", message)

    def get_logs(self) -> List[Dict]:
        """Return a copy of all collected log entries."""
        return list(self.records)

    def get_warnings_and_errors(self) -> List[Dict]:
        """Return log entries with level WARNING, ERROR, or CRITICAL."""
        return [
            log
            for log in self.records
            if log["level"] in ("WARNING", "ERROR", "CRITICAL")
        ]

    def get_summary(self) -> Dict:
        """Return total count and per-level counts."""
        summary = {"total": len(self.records), "by_level": {}}
        for log in self.records:
            level = log["level"]
            summary["by_level"][level] = summary["by_level"].get(level, 0) + 1
        return summary

    def clear(self) -> None:
        """Remove all collected log entries."""
        self.records.clear()
