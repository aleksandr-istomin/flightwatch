from aiogram import types, Router
from db_handlers.db_class import db
from utils.airport_codes import get_airport_name
from utils.aviasales_api import CURRENCY

router = Router()

@router.message(lambda msg: msg.text == "📋 Мои отслеживания")
async def list_user_trackers(message: types.Message):
    await db.connect()
    try:
        # Получаем user_id по Telegram ID
        async with db.db.execute("SELECT id FROM users WHERE telegram_id = ?", (message.from_user.id,)) as cursor:
            user = await cursor.fetchone()

        if not user:
            await message.answer("❗ Вы ещё не добавили ни одного отслеживания.")
            return

        user_id = user["id"]
        trackers = await db.get_user_trackers(user_id)

        if not trackers:
            await message.answer("🔍 У вас нет активных отслеживаний.")
            return

        response_lines = ["📡 <b>Активные отслеживания:</b>\n"]

        for t in trackers:
            response_lines.append(
                f"✈️ <b>{get_airport_name(t['origin'])}</b> → <b>{get_airport_name(t['destination'])}</b>\n"
                f"📅 Дата: <b>{t['date'][0]}</b>\n"
                f"💰 Лимит: <b>{t['price_limit']} {CURRENCY.upper()}</b>\n"
                "─────────────"
            )

        await message.answer("\n".join(response_lines))

    except Exception as e:
        print(f"Ошибка при выводе отслеживаний: {e}")
        await message.answer("⚠️ Произошла ошибка при получении списка отслеживаний.")
