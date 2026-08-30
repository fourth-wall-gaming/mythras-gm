"""Small TypeQL/id helpers, vendored so mythras-gm depends on nothing external.

These were once imported from src.skillful_alhazen.utils.skill_helpers. The skill
was decoupled from Alhazen in August 2026; this is the standalone copy.
"""
import uuid
from datetime import datetime, timezone


def escape_string(s):
    """Escape a Python string for inclusion in a double-quoted TypeQL literal."""
    if s is None:
        return ""
    return (s.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\r", ""))


def generate_id(prefix):
    """A short, collision-resistant id with a type prefix, e.g. myth-char-ab12cd34ef56."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def get_timestamp():
    """Current UTC time as a TypeQL datetime literal (T separator, no timezone)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
