from dotenv import dotenv_values
from sqlalchemy import select
from models import AppConfig


env_config = dotenv_values(".env")

ADMIN_IDS = {1371035327}

API_URL = "https://api.worldoftanks.eu/wot"
APPLICATION_ID = env_config["APPLICATION_ID"]
TOKEN = env_config["TOKEN"]

UPDATE_DELAY = 300
RPS_DELAY = 0.15  # ~6-7 RPS safe buffer


async def get_config(session):
    result = await session.execute(select(AppConfig))
    config = result.scalar_one_or_none()

    if not config:
        config = AppConfig(
            tank_id=7169,
            tank_name='T95/FV4201 Chieftain',
            games_in_tournament=100
        )
        session.add(config)
        await session.commit()
        await session.refresh(config)

    return config
