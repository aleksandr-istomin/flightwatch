from aiogram import Router, types
from aiogram.filters import Command

router = Router()

@router.message(lambda msg: msg.text == "ℹ Помощь")
async def help_button(message: types.Message):
    await message.answer(
        "🤖 Этот бот помогает отслеживать самые дешёвые авиабилеты по заданному направлению и дате.\n"    
        "🔔 Бот пришлёт уведомление, если цена билета в указанные даты опустится ниже заданной.\n\n"
        " Нажмите кнопку <b>✈ Отслеживать</b> и следуйте инструкциям."
    )

@router.message(Command("help"))
async def help_command(message: types.Message):
    await help_button(message)
