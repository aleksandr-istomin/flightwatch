from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

router = Router()

@router.message(lambda msg: msg.text == "ℹ Помощь")
async def help_button(message: types.Message, state: FSMContext):
    # Сбрасываем любые активные FSM-состояния, чтобы не перехватывали обработчики ввода города
    try:
        await state.clear()
    except Exception:
        pass
    await message.answer(
        "🤖 Этот бот помогает отслеживать самые дешёвые авиабилеты по заданному направлению и дате.\n"    
        "🔔 Бот пришлёт уведомление, если цена билета в указанные даты опустится ниже заданной.\n\n"
        " Нажмите кнопку <b>✈ Отслеживать</b> и следуйте инструкциям."
    )

@router.message(Command("help"))
async def help_command(message: types.Message, state: FSMContext):
    await help_button(message, state)
