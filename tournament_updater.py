import asyncio
from sqlalchemy import select, false
from db import SessionLocal
from models import Player, PlayerTankSnapshot, PlayerTournamentResult
from wargaming_api import fetch_tank_stats
from stats_calculator import calculate_session_stats
from datetime import datetime
from config import RPS_DELAY, get_config


async def update_players_stats(bot, force_finish=False):
    async with SessionLocal() as session:
        result = await session.execute(
            select(Player, PlayerTankSnapshot, PlayerTournamentResult)
            .join(PlayerTankSnapshot, Player.id == PlayerTankSnapshot.player_id)
            .join(PlayerTournamentResult, Player.id == PlayerTournamentResult.player_id)
            .where(PlayerTournamentResult.is_finished == false())
        )

        config = await get_config(session)
        games_in_tournament = config.games_in_tournament

        rows = result.all()

        for player, snapshot, results in rows:
            # ⚡ rate limit safety
            await asyncio.sleep(RPS_DELAY)

            current_raw = await fetch_tank_stats(
                player.account_id,
                snapshot.tank_id
            )

            if not current_raw:
                continue

            # simplified data (ONLY what you need)
            current = {
                "battles": current_raw["battles"],
                "damage_dealt": current_raw["damage_dealt"],
            }

            start = {
                "battles": snapshot.battles,
                "damage_dealt": snapshot.total_damage,
            }

            session_stats = calculate_session_stats(current, start)

            if not session_stats:
                continue

            # update ONLY what matters
            results.battles = session_stats["battles"]
            results.total_damage = session_stats["avg_damage"] * session_stats["battles"]
            results.gpg = session_stats["avg_damage"]

            # finish condition
            if session_stats["battles"] >= games_in_tournament or force_finish:
                results.is_finished = True
                results.finished_at = datetime.utcnow()

                await bot.send_message(
                    player.telegram_id,
                    "📊 Турнір завершено.\n\n"
                    f"🏁 Ви зіграли {results.battles} боїв!\n"
                    f" Ваш результат {results.gpg}!"
                )

            await session.commit()
