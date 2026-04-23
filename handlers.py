import asyncio
from aiogram.fsm.context import FSMContext

from aiogram.types import Message
from aiogram import Router, F
from aiogram.filters import Command

from sqlalchemy import select, delete, desc, false

from db import SessionLocal
from models import Player, PlayerTankSnapshot, PlayerTournamentResult
from states import RegisterState

from wargaming_api import get_tank_by_name
from register_service import register_player, create_empty_stats
from tournament_updater import update_players_stats

from config import ADMIN_IDS, RPS_DELAY, get_config

router = Router()


@router.message(F.text == "/start")
async def start(message: Message, state: FSMContext):
    telegram_id = message.from_user.id

    async with SessionLocal() as session:
        result = await session.execute(
            select(Player).where(Player.telegram_id == telegram_id)
        )
        player = result.scalar_one_or_none()

    # 👤 user already registered
    if player:
        await message.answer(
            "✅ Ви вже зареєстровані!\n\n"
            f"👤 Нік: {player.username}\n\n"
        )
        await state.clear()
        return

    # 🆕 new user → start registration
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

        config = await get_config(session)
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

    text = (
        "🏁 Турнір розпочався!\n\n"
        f"🚗 Танк: {config.tank_name}\n"
        f"🎯 Кількість боїв: {config.games_in_tournament}\n\n"
        "📊 Використовуйте команду /progress щоб переглядати свою статистику.\n\n"
        "🏆 Використовуйте команду /standings щоб переглядати статистику всіх гравців.\n\n"
    )

    for player in players:
        try:
            await message.bot.send_message(player.telegram_id, text)
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

    tank_name = None
    telegram_id = message.from_user.id

    async with SessionLocal() as session:
        config = await get_config(session)

        tank_name = config.tank_name
        games_in_tournament = config.games_in_tournament

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
        f"⚔ Бої: {results.battles} / {games_in_tournament}\n"
        f"💥 Середня шкода: {results.gpg:.2f}\n"
    )

    if results.is_finished:
        text += "\n🏁 Турнір завершено!"

    await message.answer(text)


@router.message(Command("standings"))
async def tournament_standings(message: Message):
    async with SessionLocal() as session:
        config = await get_config(session)

        tank_name = config.tank_name
        games_in_tournament = config.games_in_tournament

        result = await session.execute(
            select(Player.username, PlayerTournamentResult.gpg, PlayerTournamentResult.battles)
            .join(PlayerTournamentResult, Player.id == PlayerTournamentResult.player_id)
            .order_by(desc(PlayerTournamentResult.gpg))
        )

        rows = result.all()

    if not rows:
        await message.answer("❌ Немає даних.")
        return

    text = "<pre>\n"

    # build leaderboard text
    text += f"🏆 Турнірна таблиця\n\n🚗 Танк: {tank_name}\n\n"

    for i, (username, gpg, battles) in enumerate(rows, start=1):
        text += f"{i:>3}. {username:.<30} {gpg:0>7.2f} {battles:3}/{games_in_tournament}\n"

    text += "</pre>"

    await message.answer(text, parse_mode="HTML")


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
            f"{i}. {player.username}\n"
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


@router.message(Command("set_tank"))
async def set_tank(message: Message):

    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ You are not allowed.")
        return

    args = message.text.split(maxsplit=1)

    if len(args) < 2:
        await message.answer("Usage: /set_tank <tank name>")
        return

    query = args[1]

    tank = await get_tank_by_name(query)

    if not tank:
        await message.answer("❌ Tank not found.")
        return

    async with SessionLocal() as session:
        config = await get_config(session)

        # 🔒 prevent breaking active tournament
        result = await session.execute(
            select(PlayerTournamentResult).where(
                PlayerTournamentResult.is_finished == false()
            )
        )
        if result.first():
            await message.answer(
                "❌ Tournament is active.\n"
                "Reset it before changing tank."
            )
            return

        config.tank_id = tank["tank_id"]
        config.tank_name = tank["tank_name"]

        await session.commit()

    await message.answer(
        f"✅ Tank updated\n\n"
        f"🚗 {tank['tank_name']}\n"
        f"🆔 ID: {tank['tank_id']}"
    )


@router.message(Command("set_games"))
async def set_games(message: Message):

    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ You are not allowed.")
        return

    args = message.text.split()

    if len(args) < 2:
        await message.answer("Usage: /set_games <number>")
        return

    try:
        games = int(args[1])
    except ValueError:
        await message.answer("❌ Invalid number.")
        return

    if games <= 0:
        await message.answer("❌ Must be greater than 0.")
        return

    async with SessionLocal() as session:
        config = await get_config(session)

        # 🔒 optional safety: block if active tournament
        result = await session.execute(
            select(PlayerTournamentResult).where(
                PlayerTournamentResult.is_finished == false()
            )
        )
        if result.first():
            await message.answer(
                "❌ Tournament is active.\n"
                "Reset it before changing settings."
            )
            return

        config.games_in_tournament = games
        await session.commit()

    await message.answer(
        f"✅ Games limit updated\n\n"
        f"🎯 New limit: {games} battles"
    )


@router.message(Command("clear_stats"))
async def clear_stats(message: Message):

    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ You are not allowed.")
        return

    async with SessionLocal() as session:

        await session.execute(delete(PlayerTankSnapshot))
        await session.execute(delete(PlayerTournamentResult))

        await session.commit()

    await message.answer(
        "🧹 Tournament data cleared.\n"
        "👤 Players remain intact."
    )
