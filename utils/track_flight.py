import asyncio
from utils.aviasales_api import get_price_for_date, CURRENCY
from utils.airport_codes import get_airport_name
from create_bot import bot


async def track_flight(telegram_id: int, origin: str, destination: str, date: str,
                       price_limit: int, initial_flight: dict = None):
    first = True
    while True:
        if first and initial_flight:
            flight = initial_flight
            first = False
        else:
            flight = await get_price_for_date(origin, destination, date)
        if flight:
            price = flight.get("price", 0)
            

            if int(price) < price_limit:
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
                except Exception as e:
                    print(f"Ошибка Telegram: {e}")

        await asyncio.sleep(100)
