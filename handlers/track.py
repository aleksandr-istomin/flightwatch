from aiogram import types, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import asyncio
from datetime import datetime

from db_handlers.db_class import db
from handlers.task import user_tasks
from utils.track_flight import track_flight
from utils.airport_codes import get_airport_name, find_airports_by_city, format_airport_option
from utils.aviasales_api import CURRENCY, get_price_for_date
from utils.validators import is_valid_date
from utils.flightradar_client import get_flight_status_by_number
from utils.airlines_icao import get_airline_by_icao

router = Router()

MAX_ACTIVE_TRACKERS = 5


class FlightStatusFSM(StatesGroup):
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

@router.message(Command("track"))
async def track_command(message: types.Message):
    await db.connect()
    try:
        args = message.text.split()[1:]  # убираем /track
        if len(args) != 4:
            raise ValueError("Неверное число аргументов")

        origin = args[0].strip().upper()
        destination = args[1].strip().upper()
        dates = [d.strip() for d in args[2].split(",") if d.strip()]

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

        added_dates = []
        skipped = []  # список кортежей (date, reason)

        for date in dates:
            # 1) проверка формата/прошлого времени
            if not is_valid_date(date):
                skipped.append((date, "неверная дата (формат YYYY-MM-DD или дата в прошлом)"))
                continue

            # 2) проверка наличия слотов
            if allowed_slots <= 0:
                skipped.append((date, "нет свободных слотов (достигнут лимит)"))
                continue

            # 3) проверка через API (валидность IATA + есть ли рейсы на эту дату)
            flight = await get_price_for_date(origin, destination, date)
            if not flight or (isinstance(flight, dict) and flight.get("error")):
                skipped.append((date, "рейсы не найдены (проверь IATA-коды и дату)"))
                continue

            # 4) проверка дубликата в БД
            if await db.tracker_exists(user_id, origin, destination, date):
                skipped.append((date, "уже отслеживается"))
                continue

            # 5) всё ок — добавляем в БД и запускаем таск
            tracker_id = await db.add_flight_tracker(user_id, origin, destination, date, price_limit)

            user_tasks.setdefault(message.from_user.id, [])
            task = asyncio.create_task(
                track_flight(
                    message.from_user.id,
                    origin,
                    destination,
                    date,
                    price_limit,
                    tracker_id=tracker_id,
                    initial_flight=flight
                )
            )
            user_tasks[message.from_user.id].append(task)

            added_dates.append(date)
            allowed_slots -= 1

        # Ответ пользователю: только по реально добавленным датам
        if added_dates:
            origin_name = get_airport_name(origin) or origin
            destination_name = get_airport_name(destination) or destination
            await message.answer(
                f"📡 Отслеживаю рейсы <b>{origin_name}</b> → <b>{destination_name}</b>\n"
                f"Даты: <b>{', '.join(added_dates)}</b>\n"
                f"Цена ниже <b>{price_limit} {CURRENCY.upper()}</b>"
            )

        # Сводка по пропущенным датам (если есть)
        if skipped:
            lines = [f"• {d} — {reason}" for d, reason in skipped]
            await message.answer("⚠ Пропущены даты:\n" + "\n".join(lines))

    except Exception as e:
        print(f"Ошибка: {e}")
        await message.answer(
            "❗ Формат команды:\n<code>/track LED KGD 2025-08-04,2025-08-05 7000</code>"
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
        "&lt;даты_вылета_через_запятую&gt; &lt;максимальная_цена&gt;</code>\n\n"
        "Пример:\n"
        "<code>/track LED KGD 2025-09-08,2025-09-09 7000</code>"
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
                f"Город прилёта: {label} — {iata}\nВведите даты вылета через запятую в формате YYYY-MM-DD (напр. 2025-09-08,2025-09-09):"
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
            f"Город прилёта: {label} — {iata}\nВведите даты вылета через запятую в формате YYYY-MM-DD (напр. 2025-09-08,2025-09-09):"
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
        await message.answer("Некорректные даты. Используйте формат YYYY-MM-DD и даты не из прошлого.")
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
