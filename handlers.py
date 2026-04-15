import asyncio
from aiogram.fsm.context import FSMContext

from aiogram.types import Message
from aiogram import Router, F
from aiogram.filters import Command

from sqlalchemy import select, delete, desc

from db import SessionLocal
from models import Player, PlayerTankSnapshot, PlayerTournamentResult
from states import RegisterState

from wargaming_api import get_tank_name
from register_service import register_player, create_empty_stats
from tournament_updater import update_players_stats

from config import ADMIN_IDS, TANK_ID, GAMES_IN_TOURNAMENT, RPS_DELAY

router = Router()


@router.message(F.text == "/start")
async def start(message: Message, state: FSMContext):
    await message.answer("🎮 Надішліть свій нік в танках:")
    await state.set_state(RegisterState.waiting_for_username)


@router.message(RegisterState.waiting_for_username)
async def save_username(message: Message, state: FSMContext):
    username = message.text.strip()
    telegram_id = message.from_user.id

    loading_msg = await message.answer("⏳ Підключення до серверів WG...")

    result = await register_player(username, telegram_id)

    if not result["ok"]:
        await loading_msg.edit_text(result["error"])
        return

    await loading_msg.edit_text(
        "✅ Aкаунт успішно зареєстрований!\n\n"
        f"👤 Танковий нікнейм: {result['username']}\n"
        f"🚗 Танк: {result['tank_name']}\n\n"
        "🚀 Ви зареєстровані на турнір! Очікуйте повідомлення про початок"
    )

    await state.clear()


@router.message(Command("start_tournament"))
async def start_tournament(message: Message):

    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ You are not allowed to use this command.")
        return

    await message.answer("🚀 Initializing tournament...")

    async with SessionLocal() as session:

        result = await session.execute(select(Player))
        players = result.scalars().all()

        # 1. CREATE SNAPSHOTS FIRST (critical)
        for player in players:
            try:
                await create_empty_stats(session, player)
            except Exception:
                pass  # log later if needed

            # ⚡ rate limit safety
            await asyncio.sleep(RPS_DELAY)

        await session.commit()

    # 2. THEN broadcast (no DB work here)
    sent = 0
    failed = 0

    for player in players:
        try:
            await message.bot.send_message(
                player.telegram_id,
                "🏁 Турнір розпочався!\n\n"
                "📊 Використовуйте команду /progress щоб переглядати свою статистику.\n\n"
                "📊 Використовуйте команду /standings щоб переглядати статистику всіх гравців.\n\n"
            )
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"✅ Турнір розпочався!\n"
        f"📦 Вього гравців зареєструвалось: {len(players)}\n"
        f"📨 Беруть участь: {sent}\n"
        f"❌ Не беруть участь: {failed}"
    )


@router.message(Command("end_tournament"))
async def end_tournament(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ You are not allowed to use this command.")
        return

    await update_players_stats(message.bot, force_finish=True)
    await message.answer("🚀 Турнір завершено!")


@router.message(Command("progress"))
async def check_progress_cmd(message: Message):

    tank_name = await get_tank_name(TANK_ID)
    telegram_id = message.from_user.id

    async with SessionLocal() as session:

        # 1. get player
        result = await session.execute(
            select(Player).where(Player.telegram_id == telegram_id)
        )
        player = result.scalar_one_or_none()

        if not player:
            await message.answer("❌ Ви не зареєстровані.")
            return

        # 2. get tournament result
        result = await session.execute(
            select(PlayerTournamentResult).where(
                PlayerTournamentResult.player_id == player.id
            )
        )
        results = result.scalar_one_or_none()

        if not results:
            await message.answer("❌ Немає інформації.")
            return

    # 3. format output

    text = (
        "📊 Результат \n\n"
        f"🚗 Танк: {tank_name}\n"
        f"⚔ Бої: {results.battles} / {GAMES_IN_TOURNAMENT}\n"
        f"💥 Середня шкода: {results.gpg:.2f}\n"
    )

    if results.is_finished:
        text += "\n🏁 Турнір завершено!"

    await message.answer(text)


@router.message(Command("standings"))
async def tournament_standings(message: Message):

    tank_name = await get_tank_name(TANK_ID)

    async with SessionLocal() as session:

        result = await session.execute(
            select(Player.username, PlayerTournamentResult.gpg, PlayerTournamentResult.battles)
            .join(PlayerTournamentResult, Player.id == PlayerTournamentResult.player_id)
            .order_by(desc(PlayerTournamentResult.gpg))
        )

        rows = result.all()

    if not rows:
        await message.answer("❌ Немає даних.")
        return

    # build leaderboard text
    text = f"🏆 Турнірна таблиця\n\n🚗 Танк: {tank_name}\n\n"

    for i, (username, gpg, battles) in enumerate(rows, start=1):
        text += f"{i}. {username}: {gpg:.2f} ({battles} / {GAMES_IN_TOURNAMENT})\n"

    await message.answer(text)


@router.message(Command("participants"))
async def list_participants(message: Message):

    # 1. admin check
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ You are not allowed to use this command.")
        return

    async with SessionLocal() as session:

        result = await session.execute(select(Player))
        players = result.scalars().all()

    if not players:
        await message.answer("❌ No participants registered.")
        return

    # 2. build output
    text = "👥 Participants\n\n"

    for i, player in enumerate(players, start=1):
        text += (
            f"{i}. {player.username}"
        )

    await message.answer(text)


@router.message(Command("kick_player"))
async def kick_player(message: Message):

    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ You are not allowed.")
        return

    args = message.text.split()

    if len(args) < 2:
        await message.answer("Usage: /kick_player <username>")
        return

    username = args[1]

    async with SessionLocal() as session:

        result = await session.execute(
            select(Player).where(Player.username == username)
        )
        player = result.scalar_one_or_none()

        if not player:
            await message.answer("❌ Player not found.")
            return

        await session.execute(delete(PlayerTankSnapshot).where(PlayerTankSnapshot.player_id == player.id))
        await session.execute(delete(PlayerTournamentResult).where(PlayerTournamentResult.player_id == player.id))
        await session.execute(delete(Player).where(Player.id == player.id))

        await session.commit()

        await message.bot.send_message(
            player.telegram_id,
            f"🏁 Ви були видалені з турніру."
        )

    await message.answer(f"🗑 Player removed: {username}")


@router.message(Command("broadcast"))
async def broadcast(message: Message):

    # 1. admin check
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ You are not allowed.")
        return

    # 2. extract message text
    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Usage: /broadcast <message>")
        return

    broadcast_text = args[1]

    await message.answer("📡 Sending broadcast...")

    # 3. get all players
    async with SessionLocal() as session:
        result = await session.execute(select(Player.telegram_id))
        user_ids = result.scalars().all()

    # 4. send messages
    sent = 0
    failed = 0

    for user_id in user_ids:
        if not user_id:
            continue  # skip players without telegram_id

        try:
            await message.bot.send_message(user_id, broadcast_text)
            sent += 1
        except Exception:
            failed += 1

    # 5. report
    await message.answer(
        f"✅ Broadcast finished\n"
        f"📨 Sent: {sent}\n"
        f"❌ Failed: {failed}"
    )
