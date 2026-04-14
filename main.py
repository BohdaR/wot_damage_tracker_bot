import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from db import engine
from models import Base
from handlers import router
from tournament_updater import tournament_updater

from config import TOKEN


async def set_commands(bot):
    commands = [
        BotCommand(command="progress", description="📊 Переглянути власну статистику"),
        BotCommand(command="standings", description="📊 Переглянути турнірну таблицю"),
        BotCommand(command="start", description="🚀 Зареєструватися"),
    ]
    await bot.set_my_commands(commands)


async def main():
    # create DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    bot = Bot(token=TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(router)

    asyncio.create_task(tournament_updater(bot))

    await set_commands(bot)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
