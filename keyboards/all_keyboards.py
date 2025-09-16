from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Поиск авиабилетов"),
            KeyboardButton(text="Отслеживание авиарейсов"),
        ]
    ],
    resize_keyboard=True,
    input_field_placeholder="Выбери действие"
)

search_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="✈ Отслеживать"),
            KeyboardButton(text="❌ Остановить"),
        ],
        [
            KeyboardButton(text="📋 Мои отслеживания"),
        ],
        [
            KeyboardButton(text="ℹ Помощь"),
        ],
        [
            KeyboardButton(text="⬅ Назад"),
        ]
    ],
    resize_keyboard=True,
    input_field_placeholder="Поиск авиабилетов"
)

tracking_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🛫 Статус рейса"),
        ],
        [
            KeyboardButton(text="🕓 История полётов рейса"),
        ],
        [
            KeyboardButton(text="⬅ Назад"),
        ]
    ],
    resize_keyboard=True,
    input_field_placeholder="Отслеживание авиарейсов"
)


