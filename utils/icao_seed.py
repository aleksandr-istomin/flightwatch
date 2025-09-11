from typing import Dict, Tuple


def seed_icao_if_needed(force: bool = False) -> None:
    """Заполняет Redis ICAO-данными из локальных словарей, если ещё не заполнено.

    - Аэропорты: ключ `icao:airport:<CODE>` (HASH) с полями city, name
    - Авиакомпании: ключ `icao:airline:<CODE>` (HASH) с полями name, country
    - Маркер инициализации: `icao:seeded` = "1"
    """
    try:
        from utils.redis_client import get_redis
        from utils.airport_icao import airport_icao  # dict[str, tuple[str, str]]
        from utils.airlines_icao import airlines_icao  # dict[str, tuple[str, str]]
    except Exception:
        # Если что-то пошло не так с импортами — ничего не делаем
        return

    r = None
    try:
        r = get_redis()
        if not force:
            try:
                if r.get("icao:seeded") == "1":
                    return
            except Exception:
                # Продолжаем, попробуем сделать вставку всё равно
                pass

        pipe = r.pipeline(transaction=False)

        # Аэропорты
        try:
            for code, value in airport_icao.items():
                city, name = (value or ("", ""))
                key = f"icao:airport:{str(code).upper()}"
                pipe.hset(key, mapping={"city": city or "", "name": name or ""})
        except Exception:
            # Не прерываем — попробуем авиакомпании и маркер
            pass

        # Авиакомпании
        try:
            for code, value in airlines_icao.items():
                name, country = (value or ("", ""))
                key = f"icao:airline:{str(code).upper()}"
                pipe.hset(key, mapping={"name": name or "", "country": country or ""})
        except Exception:
            pass

        pipe.set("icao:seeded", "1")
        pipe.execute()
    except Exception:
        # Тихий фолбэк: если Redis недоступен — просто пропустим
        return

