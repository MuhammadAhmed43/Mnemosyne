from datetime import datetime, timezone


def now_utc() -> datetime:
    """Current UTC time as a naive datetime.

    Replaces the deprecated datetime.utcnow() (removed in a future Python).
    Returned naive so serialization stays identical to the prior utcnow()
    behavior (ISO string with no offset) — avoids rippling a format change
    through stored timestamps.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
