from aiogram import types, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from keyboards.all_keyboards import main_menu, search_menu, tracking_menu  # клавиатура
from db_handlers.db_class import db

router = Router()

@router.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    await db.connect()
    user_id = await db.add_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "👋 Привет! Я бот для отслеживания статусов авиарейсов и дешёвых авиабилетов.\n\n"
        "✈ Используй кнопки ниже для взаимодействия",
        reply_markup=main_menu
    )


@router.message(lambda msg: msg.text == "Поиск авиабилетов")
async def show_search_menu(message: types.Message, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    await message.answer("Выберите действие из меню поиска:", reply_markup=search_menu)


@router.message(lambda msg: msg.text == "Отслеживание авиарейсов")
async def show_tracking_menu(message: types.Message, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    await message.answer("Выберите действие:", reply_markup=tracking_menu)


@router.message(lambda msg: msg.text == "⬅ Назад")
async def back_to_main_menu(message: types.Message, state: FSMContext):
    try:
        await state.clear()
    except Exception:
        pass
    await message.answer("Возвращаю в главное меню.", reply_markup=main_menu)
