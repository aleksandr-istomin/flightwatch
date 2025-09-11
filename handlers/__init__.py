from aiogram import Dispatcher
from .start import router as start_router
from .stop import router as stop_router
from handlers.track import router as track_router
from .airport_list import router as airport_list_router
from .help import router as help_router
from .list_tracks import router as list_tracks_router


def register_handlers(dp: Dispatcher):
    dp.include_router(start_router)
    dp.include_router(stop_router)
    dp.include_router(track_router)
    dp.include_router(airport_list_router)
    dp.include_router(help_router)
    dp.include_router(list_tracks_router)
