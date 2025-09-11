from aiogram import Router
from aiogram.types import Message
from utils.airport_codes import airport_names  # словарь с кодами

router = Router()

@router.message(lambda message: message.text == "🌍 Коды аэропортов")
async def airport_list_handler(message: Message):
    lines = [f"{code} — {name}" for code, name in airport_names.items()]
    text = "🌍 Коды аэропортов:\n\n" + "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    await message.answer(text)

def register_airport_handlers(dp):
    dp.include_router(router)
