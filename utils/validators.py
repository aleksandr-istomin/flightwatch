from datetime import datetime
from typing import Optional, Union


def format_price(value: Union[int, str]) -> str:
    """Format integer price with spaces as thousands separators.

    Examples:
    7000 -> "7 000"
    "1234567" -> "1 234 567"
    """
    try:
        number = int(str(value).strip())
        return f"{number:,}".replace(",", " ")
    except Exception:
        return str(value)


def parse_user_date_to_iso(date_str: str) -> Optional[str]:
    """Parse user-entered date in DD-MM-YYYY and return ISO YYYY-MM-DD if valid and not in the past."""
    try:
        parsed = datetime.strptime(date_str.strip(), "%d-%m-%Y").date()
        if parsed < datetime.now().date():
            return None
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return None


def is_valid_date(date_str: str) -> bool:
    """Backward-compatible checker that now expects DD-MM-YYYY and not a past date."""
    return parse_user_date_to_iso(date_str) is not None


def format_iso_date_to_user(iso_date: str) -> str:
    """Format ISO date YYYY-MM-DD into DD-MM-YYYY for user display.

    If parsing fails, returns the original string.
    """
    s = (iso_date or "").strip()
    if not s:
        return s
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return s


def format_iso_datetime_to_user(value: str) -> str:
    """Format ISO datetime into DD-MM-YYYY HH:MM for user display.

    Supports strings like 2025-09-14T09:00:00+03:00 or ...Z.
    If parsing fails, returns the original string.
    """
    s = str(value or "").strip()
    if not s:
        return s
    try:
        # Python's fromisoformat doesn't accept trailing 'Z'
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt.strftime("%d-%m-%Y %H:%M")
    except Exception:
        return value
