import asyncio
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from create_bot import bot
from handlers import register_handlers
from db_handlers.db_class import db
from utils.restore_all_trackers import restore_all_trackers
from utils.icao_seed import seed_icao_if_needed


async def main():
    await db.init_db()
    # Пытаемся заполнить Redis данными ICAO (без падения при ошибке)
    try:
        seed_icao_if_needed()
    except Exception:
        pass
    dp = Dispatcher(storage=MemoryStorage())
    register_handlers(dp)
    await restore_all_trackers()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())  # <<< Запуск asyncio-цикла
