from models import Player, PlayerTournamentResult, PlayerTankSnapshot
from wargaming_api import get_account_id, fetch_tank_stats, get_tank_name

from sqlalchemy import select, delete
from db import SessionLocal

from config import TANK_ID


async def register_player(username: str, telegram_id: int):
    account_id = await get_account_id(username)

    if not account_id:
        return {"ok": False, "error": "❌ User not found. Please check your username."}

    async with SessionLocal() as session:

        # 1. get or create player
        result = await session.execute(
            select(Player).where(Player.telegram_id == telegram_id)
        )
        player = result.scalar_one_or_none()

        if player:
            player.username = username
            player.account_id = account_id
        else:
            player = Player(
                telegram_id=telegram_id,
                username=username,
                account_id=account_id
            )
            session.add(player)

        await session.commit()

        tank_name = await get_tank_name(TANK_ID)

    return {
        "ok": True,
        "username": username,
        "account_id": account_id,
        "tank_id": TANK_ID,
        "tank_name": tank_name
    }


async def create_empty_stats(session, player: Player):
    # 1. delete old tournament data
    await session.execute(
        delete(PlayerTankSnapshot).where(
            PlayerTankSnapshot.player_id == player.id
        )
    )

    await session.execute(
        delete(PlayerTournamentResult).where(
            PlayerTournamentResult.player_id == player.id
        )
    )

    # 2. fetch current API stats
    current_raw = await fetch_tank_stats(player.account_id, TANK_ID)

    if not current_raw:
        return None

    # 3. create snapshot (baseline)
    snapshot = PlayerTankSnapshot(
        player_id=player.id,
        tank_id=TANK_ID,
        battles=current_raw["battles"],
        total_damage=current_raw["damage_dealt"]
    )

    # 4. create stats record (empty state)
    stats = PlayerTournamentResult(
        player_id=player.id,
        tank_id=TANK_ID,
        battles=0,
        total_damage=0,
        gpg=0.0,
        is_finished=False
    )

    session.add(snapshot)
    session.add(stats)

    return stats
