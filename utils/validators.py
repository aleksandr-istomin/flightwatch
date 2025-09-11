from datetime import datetime

def is_valid_date(date_str: str) -> bool:
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.date() >= datetime.now().date()
    except ValueError:
        return False
