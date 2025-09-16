import asyncio
from aiogram import types, Router
from aiogram.filters import Command
from db_handlers.db_class import db
from handlers.task import user_tasks, tracker_tasks

router = Router()


@router.message(Command("stop"))
async def stop_command(message: types.Message):
    await db.connect()
    user_id = await db.add_user(message.from_user.id)  # Вернёт уже существующего
    await db.deactivate_all_user_trackers(user_id)

    chat_id = message.chat.id
    tasks = user_tasks.get(chat_id)

    if not tasks:
        await message.answer("⚠️ Нечего останавливать.")
        return

    for task in tasks:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    user_tasks.pop(chat_id, None)
    try:
        to_delete = [tid for tid, t in tracker_tasks.items() if t in tasks]
        for tid in to_delete:
            tracker_tasks.pop(tid, None)
    except Exception:
        pass

    await message.answer("❌ Все ваши отслеживания были отключены.")


@router.message(lambda msg: msg.text == "❌ Остановить")
async def stop_button(message: types.Message):
    await stop_command(message)
