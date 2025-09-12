import asyncio

from db_handlers.db_class import db
from handlers.task import user_tasks, tracker_tasks
from utils.track_flight import track_flight


async def restore_all_trackers():
    await db.connect()
    active_trackers = await db.get_active_trackers()
    for tracker in active_trackers:
        telegram_id = tracker["telegram_id"]
        if telegram_id not in user_tasks:
            user_tasks[telegram_id] = []
        task = asyncio.create_task(
            track_flight(
                telegram_id,
                tracker["origin"],
                tracker["destination"],
                tracker["date"],
                tracker["price_limit"],
                tracker_id=tracker["tracker_id"]
            )
        )
        user_tasks[telegram_id].append(task)
        # Запоминаем соответствие для точечной остановки
        tracker_tasks[tracker["tracker_id"]] = task