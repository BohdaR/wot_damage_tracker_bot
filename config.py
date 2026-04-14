from dotenv import dotenv_values
config = dotenv_values(".env")

API_URL = "https://api.worldoftanks.eu/wot"
APPLICATION_ID = config["APPLICATION_ID"]
TOKEN = config["TOKEN"]

TANK_ID = config["TANK_ID"]
ADMIN_IDS = {1371035327}

GAMES_IN_TOURNAMENT = 100
UPDATE_DELAY = 300
RPS_DELAY = 0.15  # ~6-7 RPS safe buffer
