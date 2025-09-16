import os
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, List
from fr24sdk.client import Client
from utils.airport_icao import get_airport_city_name_by_icao

async def get_flight_status_by_number(flight_number: str) -> Optional[Dict[str, Any]]:
    loop = asyncio.get_running_loop()

    def _call_sdk() -> Optional[Dict[str, Any]]:
        try:
            now = datetime.now(timezone.utc)
            dt_from = now - timedelta(hours=18)
            dt_to = now + timedelta(hours=18)

            # Хелперы для безопасного доступа к полям (dict/attr) и преобразования дат
            def safe_get(obj: Any, key: str, default: Any = "") -> Any:
                try:
                    if obj is None:
                        return default
                    if isinstance(obj, dict):
                        return obj.get(key, default)
                    return getattr(obj, key, default)
                except Exception:
                    return default

            def to_str(dt: Any) -> str:
                try:
                    if dt is None:
                        return ""
                    if isinstance(dt, datetime):
                        return dt.isoformat()
                    return str(dt)
                except Exception:
                    return ""

            def to_float(value: Any) -> Optional[float]:
                try:
                    if value is None or value == "":
                        return None
                    return float(value)
                except Exception:
                    return None

            with Client(api_token=os.getenv("FR24_API_KEY")) as client:
                # 1) Проверяем активную позицию рейса
                try:
                    live_resp = client.live.flight_positions.get_light(flights=[flight_number])
                except Exception:
                    live_resp = None

                live_data = getattr(live_resp, "data", None)
                if live_data is None and isinstance(live_resp, dict):
                    live_data = live_resp.get("data")

                active_callsign = None
                lat_value = None
                lon_value = None
                if isinstance(live_data, list) and len(live_data) > 0:
                    first = live_data[0]
                    active_callsign = safe_get(first, "callsign") or None
                    lat_value = to_float(
                        safe_get(first, "lat", None)
                        or safe_get(first, "latitude", None)
                    )
                    lon_value = to_float(
                        safe_get(first, "lon", None)
                        or safe_get(first, "lng", None)
                        or safe_get(first, "longitude", None)
                    )

                # 2) Получаем сводку рейса
                try:
                    date_from_str = dt_from.strftime("%Y-%m-%d")
                    date_to_str = dt_to.strftime("%Y-%m-%d")

                    summary = client.flight_summary.get_light(
                        flights=[flight_number],
                        flight_datetime_from=date_from_str,
                        flight_datetime_to=date_to_str,
                    )
                except Exception:
                    summary = None

                summary_data = getattr(summary, "data", None)
                if summary_data is None and isinstance(summary, dict):
                    summary_data = summary.get("data")

                if isinstance(summary_data, list) and len(summary_data) > 0:
                    item = summary_data[-1]

                    dep_code = safe_get(item, "orig_icao", "")
                    arr_code = safe_get(item, "dest_icao_actual", "") or safe_get(item, "dest_icao", "")

                    scheduled_dep = to_str(safe_get(item, "first_seen", None))
                    estimated_dep = to_str(safe_get(item, "datetime_takeoff", None))
                    scheduled_arr = to_str(safe_get(item, "last_seen", None))
                    estimated_arr = to_str(safe_get(item, "datetime_landed", None))

                    flight_ended = bool(safe_get(item, "flight_ended", False))
                    status = "scheduled"
                    if active_callsign:
                        status = "active"
                    elif flight_ended or (estimated_arr and estimated_arr <= now.isoformat()):
                        status = "landed"
                    elif estimated_dep or scheduled_dep:
                        # если взлетел, но еще не закончен
                        if estimated_dep and (not estimated_arr):
                            status = "departed"
                        else:
                            # по времени относительно now
                            latest_dep = estimated_dep or scheduled_dep
                            if latest_dep and latest_dep <= now.isoformat():
                                status = "departed"

                    airline_name = safe_get(item, "operating_as", "") or safe_get(item, "painted_as", "")
                    number_field = safe_get(item, "flight", "") or safe_get(item, "callsign", "")
                    number_final = number_field or active_callsign or flight_number

                    # Определяем город и название аэропортов по ICAO
                    dep_city, dep_name = get_airport_city_name_by_icao(dep_code)
                    arr_city, arr_name = get_airport_city_name_by_icao(arr_code)

                    result: Dict[str, Any] = {
                        "status": status,
                        "flight": {
                            "flight_number": number_final,
                            "departure": {
                                "city": dep_city,
                                "name": dep_name,
                                "scheduled": scheduled_dep,
                                "estimated": estimated_dep,
                            },
                            "arrival": {
                                "city": arr_city,
                                "name": arr_name,
                                "scheduled": scheduled_arr,
                                "estimated": estimated_arr,
                            },
                            "airline": airline_name,
                        },
                    }
                    if lat_value is not None and lon_value is not None:
                        result["position"] = {"lat": lat_value, "lon": lon_value}
                    return result

                # если сводки нет, но есть активная позиция — вернем базовую информацию
                if active_callsign:
                    result: Dict[str, Any] = {
                        "status": "active",
                        "flight": {
                            "flight_number": active_callsign or flight_number,
                            "departure": {"city": "", "name": "", "scheduled": "", "estimated": ""},
                            "arrival": {"city": "", "name": "", "scheduled": "", "estimated": ""},
                            "airline": "",
                        },
                    }
                    if lat_value is not None and lon_value is not None:
                        result["position"] = {"lat": lat_value, "lon": lon_value}
                    return result

            return None
        except Exception:
            return None

    return await loop.run_in_executor(None, _call_sdk)


async def get_flight_history_by_number(flight_number: str, days: int = 14) -> Optional[List[Dict[str, Any]]]:
    """Возвращает список прошлых рейсов для указанного авиарейса за последние N дней.

    Каждый элемент списка содержит информацию о вылете/прилёте, статус, аэропорты (по ICAO),
    времена в ISO-строках, авиакомпанию и финальный номер рейса (если был callsign).
    """
    loop = asyncio.get_running_loop()

    def _call_sdk_hist() -> Optional[List[Dict[str, Any]]]:
        try:
            now = datetime.now(timezone.utc)
            dt_from = now - timedelta(days=max(1, int(days)))
            date_from_str = dt_from.strftime("%Y-%m-%d")
            date_to_str = now.strftime("%Y-%m-%d")

            def safe_get(obj: Any, key: str, default: Any = "") -> Any:
                try:
                    if obj is None:
                        return default
                    if isinstance(obj, dict):
                        return obj.get(key, default)
                    return getattr(obj, key, default)
                except Exception:
                    return default

            def to_str(dt: Any) -> str:
                try:
                    if dt is None:
                        return ""
                    if isinstance(dt, datetime):
                        return dt.isoformat()
                    return str(dt)
                except Exception:
                    return ""

            def parse_iso(value: Any) -> Optional[datetime]:
                try:
                    s = to_str(value)
                    if not s:
                        return None
                    if s.endswith("Z"):
                        s = s[:-1] + "+00:00"
                    return datetime.fromisoformat(s)
                except Exception:
                    return None

            with Client(api_token=os.getenv("FR24_API_KEY")) as client:
                try:
                    summary = client.flight_summary.get_light(
                        flights=[flight_number],
                        flight_datetime_from=date_from_str,
                        flight_datetime_to=date_to_str,
                    )
                except Exception:
                    summary = None

                data = getattr(summary, "data", None)
                if data is None and isinstance(summary, dict):
                    data = summary.get("data")

                if not isinstance(data, list) or not data:
                    return []

                history: List[Dict[str, Any]] = []
                for item in data:
                    dep_code = safe_get(item, "orig_icao", "")
                    arr_code = safe_get(item, "dest_icao_actual", "") or safe_get(item, "dest_icao", "")

                    scheduled_dep = to_str(safe_get(item, "first_seen", None))
                    actual_dep = to_str(safe_get(item, "datetime_takeoff", None))
                    scheduled_arr = to_str(safe_get(item, "last_seen", None))
                    actual_arr = to_str(safe_get(item, "datetime_landed", None))

                    airline_name = safe_get(item, "operating_as", "") or safe_get(item, "painted_as", "")
                    number_field = safe_get(item, "flight", "") or safe_get(item, "callsign", "")
                    number_final = number_field or flight_number

                    aircraft_model = safe_get(item, "aircraft", "") or safe_get(item, "model", "")
                    aircraft_icao = safe_get(item, "aircraft_icao", "")
                    registration = safe_get(item, "registration", "") or safe_get(item, "reg", "")
                    distance_val = safe_get(item, "distance", None)
                    try:
                        distance_km = None
                        if distance_val is not None and str(distance_val).strip() != "":
                            # Пытаемся привести к километрам
                            d = float(distance_val)
                            distance_km = int(round(d))
                    except Exception:
                        distance_km = None

                    dt_sched_dep = parse_iso(scheduled_dep)
                    dt_act_dep = parse_iso(actual_dep)
                    dt_sched_arr = parse_iso(scheduled_arr)
                    dt_act_arr = parse_iso(actual_arr)

                    duration_min = None
                    if dt_act_dep and dt_act_arr:
                        try:
                            duration_min = int((dt_act_arr - dt_act_dep).total_seconds() // 60)
                        except Exception:
                            duration_min = None

                    delay_dep_min = None
                    if dt_sched_dep and dt_act_dep:
                        try:
                            delay_dep_min = int((dt_act_dep - dt_sched_dep).total_seconds() // 60)
                        except Exception:
                            delay_dep_min = None

                    delay_arr_min = None
                    if dt_sched_arr and dt_act_arr:
                        try:
                            delay_arr_min = int((dt_act_arr - dt_sched_arr).total_seconds() // 60)
                        except Exception:
                            delay_arr_min = None

                    dep_city, dep_name = get_airport_city_name_by_icao(dep_code)
                    arr_city, arr_name = get_airport_city_name_by_icao(arr_code)

                    history.append({
                        "flight_number": number_final,
                        "airline": airline_name,
                        "departure": {
                            "icao": dep_code,
                            "city": dep_city,
                            "name": dep_name,
                            "scheduled": scheduled_dep,
                            "actual": actual_dep,
                        },
                        "arrival": {
                            "icao": arr_code,
                            "city": arr_city,
                            "name": arr_name,
                            "scheduled": scheduled_arr,
                            "actual": actual_arr,
                        },
                        "aircraft": {
                            "model": aircraft_model,
                            "icao": aircraft_icao,
                            "registration": registration,
                        },
                        "duration_min": duration_min,
                        "distance_km": distance_km,
                        "delay": {
                            "departure_min": delay_dep_min,
                            "arrival_min": delay_arr_min,
                        }
                    })

                return history
        except Exception:
            return None

    return await loop.run_in_executor(None, _call_sdk_hist)
