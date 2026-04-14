import asyncio
from sqlalchemy import select, false
from db import SessionLocal
from models import Player, PlayerTankSnapshot, PlayerTournamentResult
from wargaming_api import fetch_tank_stats
from stats_calculator import calculate_session_stats
from config import GAMES_IN_TOURNAMENT, UPDATE_DELAY, RPS_DELAY


async def tournament_updater(bot):
    while True:
        async with SessionLocal() as session:
            result = await session.execute(
                select(Player, PlayerTankSnapshot, PlayerTournamentResult)
                .join(PlayerTankSnapshot, Player.id == PlayerTankSnapshot.player_id)
                .join(PlayerTournamentResult, Player.id == PlayerTournamentResult.player_id)
                .where(PlayerTournamentResult.is_finished == false())
            )

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
                if session_stats["battles"] >= GAMES_IN_TOURNAMENT:
                    results.is_finished = True

                    await bot.send_message(
                        player.telegram_id,
                        f"🏁 Ви зіграли {GAMES_IN_TOURNAMENT} боїв!\n"
                        "📊 Турнір завершено."
                        f" Ваш результат {results.gpg} за {results.battles} боїв!"
                    )

                await session.commit()

        # global cooldown between cycles
        await asyncio.sleep(UPDATE_DELAY)
