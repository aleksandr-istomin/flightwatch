from aiogram import types, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import asyncio
from datetime import datetime

from db_handlers.db_class import db
from handlers.task import user_tasks, tracker_tasks
from utils.track_flight import track_flight
from utils.airport_codes import get_airport_name, find_airports_by_city, format_airport_option
from utils.aviasales_api import CURRENCY, get_price_for_date
from utils.validators import is_valid_date, parse_user_date_to_iso, format_iso_date_to_user, format_price
from utils.flightradar_client import get_flight_status_by_number
from utils.airlines_icao import get_airline_by_icao

router = Router()

MAX_ACTIVE_TRACKERS = 5


class FlightStatusFSM(StatesGroup):
    waiting_flight_number = State()


class FlightHistoryFSM(StatesGroup):
    waiting_flight_number = State()


class TrackFSM(StatesGroup):
    waiting_origin_city = State()
    waiting_destination_city = State()
    waiting_dates = State()
    waiting_price = State()


@router.message(lambda msg: msg.text == "🛫 Статус рейса")
async def ask_flight_number(message: types.Message, state: FSMContext):
    await state.set_state(FlightStatusFSM.waiting_flight_number)
    await message.answer("Введите номер рейса, например: <b>SU100</b> или <b>AF1234</b>")


@router.message(FlightStatusFSM.waiting_flight_number)
async def handle_flight_number(message: types.Message, state: FSMContext):
    def format_dt(value: str) -> str:
        s = str(value or "").strip()
        if not s:
            return ""
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            return dt.strftime("%d-%m-%Y %H:%M")
        except Exception:
            return s

    flight_number = (message.text or "").strip().upper().replace(" ", "")
    if not flight_number or len(flight_number) < 3:
        await message.answer("❗ Укажите корректный номер рейса, например: <b>SU100</b>")
        return

    await message.answer("⏳ Запрашиваю статус рейса...")
    data = await get_flight_status_by_number(flight_number)
    await state.clear()

    if not data:
        await message.answer("⚠️ Не удалось получить статус рейса. Попробуйте позже или проверьте номер рейса.")
        return

    status = data.get("status", "unknown")
    flight = data.get("flight", {}) or {}
    dep = flight.get("departure", {})
    arr = flight.get("arrival", {})
    dep_city = dep.get('city', '')
    dep_name = dep.get('name', '')
    arr_city = arr.get('city', '')
    arr_name = arr.get('name', '')

    dep_label = f"{dep_city} ({dep_name})" if dep_city or dep_name else "—"
    arr_label = f"{arr_city} ({arr_name})" if arr_city or arr_name else "—"

    # Авиакомпания: если в ответе пришёл ICAO-код (3 буквы), маппим на название и страну
    airline_raw = str(flight.get('airline', '') or '').strip()
    airline_line = f"Авиакомпания: {airline_raw}"
    maybe_code = airline_raw.upper()
    if len(maybe_code) == 3 and maybe_code.isalpha():
        name, country = get_airline_by_icao(maybe_code)
        if name or country:
            airline_line = f"Авиакомпания: {name}{f' ({country})' if country else ''}"

    text = (
        f"✈️ Рейс <b>{flight.get('flight_number', flight_number)}</b>\n"
        f"📋 Статус: <b>{status}</b>\n"
        f"────────────────────────\n"
        f"🛫 <b>Вылет:</b> {dep_label}\n"
        f"• 📅 по расписанию: {format_dt(dep.get('scheduled',''))}\n"
        f"• ⏱ оценочно: {format_dt(dep.get('estimated',''))}\n"
        f"🛬 <b>Прилет:</b> {arr_label}\n"
        f"• 📅 по расписанию: {format_dt(arr.get('scheduled',''))}\n"
        f"• ⏱ оценочно: {format_dt(arr.get('estimated',''))}\n"
        f"🏷 {airline_line}"
    )
    await message.answer(text)

    # Если удалось получить текущие координаты самолёта — отправим карту следующим сообщением
    pos = data.get("position") if isinstance(data, dict) else None
    if isinstance(pos, dict):
        lat = pos.get("lat")
        lon = pos.get("lon")
        try:
            if lat is not None and lon is not None:
                # Яндекс Статические карты требуют порядок lon,lat
                lon_str = str(lon)
                lat_str = str(lat)
                map_url = (
                    "https://static-maps.yandex.ru/1.x/?"
                    f"ll={lon_str},{lat_str}&"
                    "z=6&size=600,400&l=map&"
                    f"pt={lon_str},{lat_str},pm2rdm"
                )
                await message.answer_photo(map_url, caption="Текущая позиция самолёта")
        except Exception:
            # Молча игнорируем ошибки с внешним сервисом карт, чтобы не мешать основному сценарию
            pass


@router.message(lambda msg: msg.text == "🕓 История полётов рейса")
async def ask_history_flight_number(message: types.Message, state: FSMContext):
    await state.set_state(FlightHistoryFSM.waiting_flight_number)
    await message.answer("Введите номер рейса для отображения истории, например: <b>SU100</b>")


@router.message(FlightHistoryFSM.waiting_flight_number)
async def handle_history_flight_number(message: types.Message, state: FSMContext):
    from utils.flightradar_client import get_flight_history_by_number

    flight_number = (message.text or "").strip().upper().replace(" ", "")
    if not flight_number or len(flight_number) < 3:
        await message.answer("❗ Укажите корректный номер рейса, например: <b>SU100</b>")
        return

    await message.answer("⏳ Загружаю историю рейсов...")
    history = await get_flight_history_by_number(flight_number, days=14)
    await state.clear()

    if not history:
        await message.answer("⚠️ История рейсов не найдена. Попробуйте другой номер.")
        return

    # Ограничим вывод первыми 12 записями, оформив как в статусе рейса
    lines = []
    count = 0
    for item in history:
        dep = item.get("departure", {})
        arr = item.get("arrival", {})
        aircraft = item.get("aircraft", {})
        delay = item.get("delay", {})

        dep_city = dep.get('city', '')
        dep_name = dep.get('name', '')
        arr_city = arr.get('city', '')
        arr_name = arr.get('name', '')

        dep_label = f"{dep_city} ({dep_name})" if dep_city or dep_name else (dep.get('icao', '—'))
        arr_label = f"{arr_city} ({arr_name})" if arr_city or arr_name else (arr.get('icao', '—'))

        airline_line = item.get('airline', '')
        flight_num = item.get('flight_number', flight_number)

        duration_line = ""
        if item.get('duration_min') is not None:
            duration_line = f"• ⏱ длительность: {_fmt_minutes_to_hhmm(item['duration_min'])}"

        delay_dep_line = ""
        if delay.get('departure_min') is not None:
            dd = delay['departure_min']
            sign = "+" if dd and dd > 0 else ""
            delay_dep_line = f"• ⌛ отклонение вылета: {sign}{dd} мин"

        delay_arr_line = ""
        if delay.get('arrival_min') is not None:
            da = delay['arrival_min']
            sign = "+" if da and da > 0 else ""
            delay_arr_line = f"• ⌛ отклонение прилёта: {sign}{da} мин"

        distance_line = ""
        if item.get('distance_km') is not None:
            distance_line = f"• 📏 дистанция: {item['distance_km']} км"

        ac_parts = []
        if aircraft.get('model'):
            ac_parts.append(aircraft['model'])
        if aircraft.get('icao'):
            ac_parts.append(aircraft['icao'])
        if aircraft.get('registration'):
            ac_parts.append(aircraft['registration'])
        aircraft_line = f"🛩 Самолёт: {' / '.join(ac_parts)}" if ac_parts else ""

        text = (
            f"✈️ Рейс <b>{flight_num}</b>\n"
            f"🏷 Авиакомпания: {airline_line}\n"
            f"────────────────────────\n"
            f"🛫 <b>Вылет:</b> {dep_label}\n"
            f"• 📅 по расписанию: {_fmt_dt(dep.get('scheduled',''))}\n"
            f"• ⏱ фактически: {_fmt_dt(dep.get('actual',''))}\n"
            f"🛬 <b>Прилет:</b> {arr_label}\n"
            f"• 📅 по расписанию: {_fmt_dt(arr.get('scheduled',''))}\n"
            f"• ⏱ фактически: {_fmt_dt(arr.get('actual',''))}\n"
            f"{duration_line}\n"
            f"{delay_dep_line}\n"
            f"{delay_arr_line}\n"
            f"{distance_line}\n"
            f"{aircraft_line}"
        )
        # Удалим пустые строки
        text = "\n".join([ln for ln in text.splitlines() if ln.strip()])
        lines.append(text)
        count += 1
        if count >= 12:
            break

    await message.answer("\n\n".join(lines))


def _fmt_dt(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        return dt.strftime("%d-%m-%Y %H:%M")
    except Exception:
        return value


def _fmt_minutes_to_hhmm(total_min):
    try:
        m = int(total_min)
    except Exception:
        return ""
    if m < 0:
        m = -m
    h = m // 60
    mm = m % 60
    return f"{h:02d}:{mm:02d}"

@router.message(Command("track"))
async def track_command(message: types.Message):
    await db.connect()
    try:
        args = message.text.split()[1:]  # убираем /track
        if len(args) != 4:
            raise ValueError("Неверное число аргументов")

        origin = args[0].strip().upper()
        destination = args[1].strip().upper()
        dates_raw = [d.strip() for d in args[2].split(",") if d.strip()]

        try:
            price_limit = int(args[3])
        except ValueError:
            await message.answer("❗ Неверный формат цены. Пример: 7000")
            return

        user_id = await db.add_user(message.from_user.id, message.from_user.username)
        active_count = await db.count_active_trackers(user_id)
        allowed_slots = MAX_ACTIVE_TRACKERS - active_count

        if allowed_slots <= 0:
            await message.answer(
                f"⚠ У вас уже {active_count} активных отслеживаний. "
                f"Максимум разрешено {MAX_ACTIVE_TRACKERS}."
            )
            return

        added_dates_user = []
        skipped = []  # список кортежей (date, reason)
        to_start = []  # список параметров для запуска трекеров после уведомления

        for date_user in dates_raw:
            # 1) проверка формата/прошлого времени (ожидаем ДД-ММ-ГГГГ)
            iso_date = parse_user_date_to_iso(date_user)
            if not iso_date:
                skipped.append((date_user, "неверная дата (формат ДД-ММ-ГГГГ или дата в прошлом)"))
                continue

            # 2) проверка наличия слотов
            if allowed_slots <= 0:
                skipped.append((date_user, "нет свободных слотов (достигнут лимит)"))
                continue

            # 3) проверка через API (валидность IATA + есть ли рейсы на эту дату)
            flight = await get_price_for_date(origin, destination, iso_date)
            if not flight or (isinstance(flight, dict) and flight.get("error")):
                skipped.append((date_user, "рейсы не найдены (проверь IATA-коды и дату)"))
                continue

            # 4) проверка дубликата в БД
            if await db.tracker_exists(user_id, origin, destination, iso_date):
                skipped.append((date_user, "уже отслеживается"))
                continue

            # 5) всё ок — добавляем в БД и запускаем таск
            tracker_id = await db.add_flight_tracker(user_id, origin, destination, iso_date, price_limit)

            # отложим запуск, чтобы сначала отправить статусное сообщение
            to_start.append((tracker_id, iso_date, flight))

            added_dates_user.append(format_iso_date_to_user(iso_date))
            allowed_slots -= 1

        # Ответ пользователю: только по реально добавленным датам
        if added_dates_user:
            origin_name = get_airport_name(origin) or origin
            destination_name = get_airport_name(destination) or destination
            await message.answer(
                f"📡 Отслеживаю рейсы <b>{origin_name}</b> → <b>{destination_name}</b>\n"
                f"Даты: <b>{', '.join(added_dates_user)}</b>\n"
                f"Цена ниже <b>{format_price(price_limit)} {CURRENCY.upper()}</b>"
            )

            # теперь запускаем трекеры, чтобы предложения пришли после статусного сообщения
            user_tasks.setdefault(message.from_user.id, [])
            for tracker_id, iso_date, initial_flight in to_start:
                task = asyncio.create_task(
                    track_flight(
                        message.from_user.id,
                        origin,
                        destination,
                        iso_date,
                        price_limit,
                        tracker_id=tracker_id,
                        initial_flight=initial_flight
                    )
                )
                user_tasks[message.from_user.id].append(task)
                tracker_tasks[tracker_id] = task

        # Сводка по пропущенным датам (если есть)
        if skipped:
            lines = [f"• {d} — {reason}" for d, reason in skipped]
            await message.answer("⚠ Пропущены даты:\n" + "\n".join(lines))

    except Exception as e:
        print(f"Ошибка: {e}")
        await message.answer(
            "❗ Формат команды:\n<code>/track LED KGD 04-08-2025,05-08-2025 7000</code>"
        )


@router.message(lambda msg: msg.text == "✈ Отслеживать")
async def track_button_handler(message: types.Message, state: FSMContext):
    # Запускаем диалог по сбору данных в человеко-понятном виде
    await state.set_state(TrackFSM.waiting_origin_city)
    await message.answer("Введите город вылета (например: Москва):")


@router.message(lambda msg: msg.text == "Отслеживание авиарейсов")
async def tracking_info_handler(message: types.Message):
    await message.answer(
        "📡 Отслеживание авиарейсов позволяет получать уведомления о снижении цены.\n\n"
        "Введи команду в формате:\n"
        "<code>/track &lt;код_города_вылета&gt; &lt;код_города_прилёта&gt; "
        "&lt;даты_вылета_через_запятую в формате ДД-ММ-ГГГГ&gt; &lt;максимальная_цена&gt;</code>\n\n"
        "Пример:\n"
        "<code>/track LED KGD 08-09-2025,09-09-2025 7000</code>"
    )


# ===== Диалог FSM для отслеживания по городам/датам/цене =====

@router.message(TrackFSM.waiting_origin_city)
async def handle_origin_city(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()

    # Попытка выбора из ранее предложенного списка
    if text.isdigit() and data.get("origin_options"):
        idx = int(text) - 1
        options = data.get("origin_options") or []
        if 0 <= idx < len(options):
            iata, label = options[idx]
            await state.update_data(origin=iata, origin_options=None)
            await state.set_state(TrackFSM.waiting_destination_city)
            await message.answer(f"Город вылета: {label} — {iata}\nВведите город прилёта:")
            return

    # Иначе — воспринимаем как ввод города
    options = find_airports_by_city(text)
    if not options:
        await message.answer("Не нашёл аэропорты для этого города. Попробуйте ещё раз.")
        return
    if len(options) == 1:
        iata, label = options[0]
        await state.update_data(origin=iata)
        await state.set_state(TrackFSM.waiting_destination_city)
        await message.answer(f"Город вылета: {label} — {iata}\nВведите город прилёта:")
        return
    list_text = "Нашёл несколько аэропортов. Выберите номер:\n" + "\n".join(
        [f"{idx+1}. {format_airport_option(iata, label)}" for idx, (iata, label) in enumerate(options[:10])]
    )
    await state.update_data(origin_options=options[:10])
    await message.answer(list_text)


@router.message(TrackFSM.waiting_destination_city)
async def handle_destination_city(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()

    # Попытка выбора из списка
    if text.isdigit() and data.get("destination_options"):
        idx = int(text) - 1
        options = data.get("destination_options") or []
        if 0 <= idx < len(options):
            iata, label = options[idx]
            await state.update_data(destination=iata, destination_options=None)
            await state.set_state(TrackFSM.waiting_dates)
            await message.answer(
                f"Город прилёта: {label} — {iata}\nВведите даты вылета через запятую в формате ДД-ММ-ГГГГ (напр. 08-09-2025,09-09-2025):"
            )
            return

    # Иначе — анализ города
    options = find_airports_by_city(text)
    if not options:
        await message.answer("Не нашёл аэропорты для этого города. Попробуйте ещё раз.")
        return
    if len(options) == 1:
        iata, label = options[0]
        await state.update_data(destination=iata)
        await state.set_state(TrackFSM.waiting_dates)
        await message.answer(
            f"Город прилёта: {label} — {iata}\nВведите даты вылета через запятую в формате ДД-ММ-ГГГГ (напр. 08-09-2025,09-09-2025):"
        )
        return
    list_text = "Нашёл несколько аэропортов. Выберите номер:\n" + "\n".join(
        [f"{idx+1}. {format_airport_option(iata, label)}" for idx, (iata, label) in enumerate(options[:10])]
    )
    await state.update_data(destination_options=options[:10])
    await message.answer(list_text)


@router.message(TrackFSM.waiting_dates)
async def handle_dates(message: types.Message, state: FSMContext):
    raw = (message.text or "").strip()
    dates = [d.strip() for d in raw.split(",") if d.strip()]
    bad = [d for d in dates if not is_valid_date(d)]
    if not dates or bad:
        await message.answer("Некорректные даты. Используйте формат ДД-ММ-ГГГГ и даты не из прошлого.")
        return
    await state.update_data(dates=dates)
    await message.answer("Введите максимальную цену (целое число):")
    await state.set_state(TrackFSM.waiting_price)


@router.message(TrackFSM.waiting_price)
async def handle_price(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    try:
        price_limit = int(text)
    except ValueError:
        await message.answer("Некорректная цена. Введите целое число, например: 7000")
        return

    data = await state.get_data()
    origin = data.get("origin")
    destination = data.get("destination")
    dates = data.get("dates", [])

    # Запускаем существующую логику через /track, чтобы переиспользовать проверки
    cmd = f"/track {origin} {destination} {','.join(dates)} {price_limit}"
    fake = message.model_copy(update={"text": cmd})
    await state.clear()
    await track_command(fake)
