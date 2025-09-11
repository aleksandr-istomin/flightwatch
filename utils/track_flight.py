import asyncio
from typing import Optional
from utils.aviasales_api import get_price_for_date, CURRENCY
from utils.airport_codes import get_airport_name
from create_bot import bot
from db_handlers.db_class import db


async def track_flight(telegram_id: int, origin: str, destination: str, date: str,
                       price_limit: int, tracker_id: Optional[int] = None, initial_flight: dict = None):
    first = True
    while True:
        if first and initial_flight:
            flight = initial_flight
            first = False
        else:
            flight = await get_price_for_date(origin, destination, date)
        if flight:
            price = flight.get("price", 0)
            try:
                price_int = int(price)
            except Exception:
                price_int = 0

            # Получаем последнюю отправленную цену по трекеру (если id известен)
            last_sent = None
            if tracker_id is not None:
                try:
                    last_sent = await db.get_last_sent_price(tracker_id)
                except Exception:
                    last_sent = None

            should_notify = False
            if price_int < price_limit:
                if last_sent is None or price_int < int(last_sent):
                    should_notify = True

            if should_notify:
                airline = flight.get("airline", "").upper()
                departure = flight.get("departure_at", "")
                link = flight.get("link", "")
                message_text = (
                    f"✈️ <b>{get_airport_name(origin)}</b> → <b>{get_airport_name(destination)}</b>\n"
                    f"📅 Дата: <b>{date}</b>\n"
                    f"Цена: <b>{price} {CURRENCY.upper()}</b>\n"
                    f"Авиакомпания: <b>{airline}</b>\n"
                    f"Вылет: {departure}\n"
                    f"<a href='https://www.aviasales.ru{link}'>🔗 Купить билет</a>"
                )
                try:
                    await bot.send_message(telegram_id, message_text)
                    if tracker_id is not None:
                        try:
                            await db.update_last_sent_price(tracker_id, price_int)
                        except Exception:
                            pass
                except Exception as e:
                    print(f"Ошибка Telegram: {e}")

        await asyncio.sleep(100)
