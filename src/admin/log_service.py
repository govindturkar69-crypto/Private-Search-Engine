"""Log service for bounded, redacted application log retrieval."""

from collections import deque
import logging
from pathlib import Path
import re
from typing import List, Optional

from src.api.admin_models import LogEntry

logger = logging.getLogger(__name__)

# Sensitive token/secret redaction patterns
REDACTION_PATTERNS = [
    (
        re.compile(
            r"(?i)((?:admin[-_]?)?token|api[-_]?key|password|secret|authorization)"
            r"[:=]\s*([^\s,;'\"]+)"
        ),
        r"\1=***REDACTED***",
    ),
    (
        re.compile(r"(?i)bearer\s+([a-zA-Z0-9_\-\.]{8,})"),
        r"Bearer ***REDACTED***",
    ),
    (
        re.compile(r"(?i)x-admin-token[:=]\s*([^\s,;'\"]+)"),
        r"X-Admin-Token: ***REDACTED***",
    ),
]


def redact_sensitive_data(text: str) -> str:
    """Redact tokens, passwords, and sensitive keys from log text."""
    redacted = text
    for pattern, repl in REDACTION_PATTERNS:
        redacted = pattern.sub(repl, redacted)
    return redacted


class LogService:
    """Reads and parses bounded tails of application log files with redaction."""

    def __init__(self, log_path: str = "data/app.log") -> None:
        self.log_path = Path(log_path)

    def parse_line(self, raw_line: str) -> LogEntry:
        """Parse a single formatted log line into a typed LogEntry."""
        cleaned = redact_sensitive_data(raw_line.strip())
        parts = cleaned.split(" - ", 3)
        if len(parts) == 4:
            return LogEntry(
                timestamp=parts[0].strip(),
                module=parts[1].strip(),
                level=parts[2].strip().upper(),
                message=parts[3].strip(),
            )
        # Fallback for multiline tracebacks or non-standard formatting
        return LogEntry(
            timestamp="",
            module="system",
            level="INFO",
            message=cleaned,
        )

    def get_logs(
        self,
        lines: int = 100,
        level: Optional[str] = None,
    ) -> List[LogEntry]:
        """Retrieve bounded tail of log entries with optional level filtering."""
        # Enforce strict bounds (1 to 500 lines)
        clamped_lines = max(1, min(lines, 500))

        if not self.log_path.exists():
            return []

        filter_level = level.upper() if level else None
        collected: deque[str] = deque(
            maxlen=clamped_lines * 3 if filter_level else clamped_lines
        )

        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.strip():
                        collected.append(line)
        except Exception as e:
            logger.error(f"Error reading log file at {self.log_path}: {e}")
            return []

        entries: List[LogEntry] = []
        for raw in collected:
            entry = self.parse_line(raw)
            if filter_level and entry.level != filter_level:
                continue
            entries.append(entry)

        # Slice to the requested maximum lines from tail
        return entries[-clamped_lines:]
