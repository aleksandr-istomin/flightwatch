from aiogram import types, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db_handlers.db_class import db
from utils.airport_codes import get_airport_name
from utils.aviasales_api import CURRENCY
from utils.validators import format_iso_date_to_user, format_price
from handlers.task import tracker_tasks

router = Router()

@router.message(lambda msg: msg.text == "📋 Мои отслеживания")
async def list_user_trackers(message: types.Message, state: FSMContext):
    await db.connect()
    try:
        # Сбрасываем FSM, чтобы пользовательский ввод не перехватывали состояния поиска городов
        try:
            await state.clear()
        except Exception:
            pass
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

        kb_rows = []
        for t in trackers:
            title = (
                f"{get_airport_name(t['origin'])} → {get_airport_name(t['destination'])} | "
                f"{format_iso_date_to_user(t['date'][0])} | ≤ {format_price(t['price_limit'])} {CURRENCY.upper()}"
            )
            kb_rows.append([
                InlineKeyboardButton(text=title, callback_data=f"stop_tr_{t['tracker_id']}")
            ])

        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await message.answer("📡 <b>Активные отслеживания:</b>", reply_markup=kb)

    except Exception as e:
        print(f"Ошибка при выводе отслеживаний: {e}")
        await message.answer("⚠️ Произошла ошибка при получении списка отслеживаний.")


@router.callback_query(lambda c: c.data and c.data.startswith("stop_tr_"))
async def stop_selected_tracker(callback: types.CallbackQuery):
    try:
        tracker_id_str = callback.data.replace("stop_tr_", "", 1)
        tracker_id = int(tracker_id_str)
    except Exception:
        await callback.answer("Некорректный идентификатор", show_alert=False)
        return

    # Отключаем в БД
    try:
        await db.connect()
        await db.deactivate_tracker(tracker_id)
    except Exception:
        pass

    # Останавливаем соответствующую задачу, если есть
    task = tracker_tasks.pop(tracker_id, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except Exception:
            pass

    await callback.answer("Отслеживание остановлено")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ Отслеживание отключено.")
