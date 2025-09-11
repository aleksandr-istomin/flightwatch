import os
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
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
                    # Пытаемся извлечь координаты из разных возможных названий полей
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

                    # Новая схема: плоские поля
                    dep_code = safe_get(item, "orig_icao", "")
                    arr_code = safe_get(item, "dest_icao_actual", "") or safe_get(item, "dest_icao", "")

                    scheduled_dep = to_str(safe_get(item, "first_seen", None))
                    estimated_dep = to_str(safe_get(item, "datetime_takeoff", None))
                    scheduled_arr = to_str(safe_get(item, "last_seen", None))
                    estimated_arr = to_str(safe_get(item, "datetime_landed", None))

                    # Определение статуса
                    flight_ended = bool(safe_get(item, "flight_ended", False))
                    status = "scheduled"
                    if active_callsign:
                        status = "active"
                    elif flight_ended or (estimated_arr and estimated_arr <= now.isoformat()):
                        status = "landed"
                    elif estimated_dep or scheduled_dep:
                        # Если взлетел, но еще не закончен
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

                # Если сводки нет, но есть активная позиция — вернем базовую информацию
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
