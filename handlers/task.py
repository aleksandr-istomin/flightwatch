user_tasks = {}  # ключ: telegram_id, значение: список asyncio.Task

# Маппинг tracker_id -> asyncio.Task для точечной остановки
# Ключ: tracker_id (int), значение: asyncio.Task
tracker_tasks = {}
