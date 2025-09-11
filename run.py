import asyncio
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from create_bot import bot
from handlers import register_handlers
from db_handlers.db_class import db
from utils.restore_all_trackers import restore_all_trackers


async def main():
    await db.init_db()
    dp = Dispatcher(storage=MemoryStorage())
    register_handlers(dp)
    await restore_all_trackers()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())  # <<< Запуск asyncio-цикла
