import os
import aiohttp

API_TOKEN = os.getenv("API_TOKEN")
CURRENCY = "rub"
ONE_WAY = "true"
DIRECT = "false"
async def get_price_for_date(origin: str, destination: str, date_str: str):
    url = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": date_str,
        "token": API_TOKEN,
        "cy": CURRENCY,
        "one_way": ONE_WAY,
        "direct": DIRECT,
        "limit": 10,
        "page": 1,
        "sorting": "price",
        "unique": "false"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                data = await response.json()
                if not data.get("success", False):
                    return {"error": "api_error"}

                flights = data.get("data", [])
                return flights[0] if flights else None
    except Exception as e:
        print(f"Ошибка при получении данных: {e}")
        return None
