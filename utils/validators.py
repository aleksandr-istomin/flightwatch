from datetime import datetime
from typing import Optional, Union


def format_price(value: Union[int, str]) -> str:
    try:
        number = int(str(value).strip())
        return f"{number:,}".replace(",", " ")
    except Exception:
        return str(value)


def parse_user_date_to_iso(date_str: str) -> Optional[str]:
    try:
        parsed = datetime.strptime(date_str.strip(), "%d-%m-%Y").date()
        if parsed < datetime.now().date():
            return None
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        return None


def is_valid_date(date_str: str) -> bool:
    return parse_user_date_to_iso(date_str) is not None


def format_iso_date_to_user(iso_date: str) -> str:
    s = (iso_date or "").strip()
    if not s:
        return s
    try:
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.strftime("%d-%m-%Y")
    except Exception:
        return s


def format_iso_datetime_to_user(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return s
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt.strftime("%d-%m-%Y %H:%M")
    except Exception:
        return value
