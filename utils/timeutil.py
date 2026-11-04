"""UTC timestamps without the deprecated datetime.utcnow()."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC now, matching the existing SQLite DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
