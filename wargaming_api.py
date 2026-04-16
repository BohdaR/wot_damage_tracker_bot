import aiohttp
from config import APPLICATION_ID, API_URL


async def fetch(endpoint: str, params: dict):
    url = f"{API_URL}/{endpoint}/"

    params["application_id"] = APPLICATION_ID

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            return await response.json()


async def get_account_id(username: str):
    data = await fetch("account/list", {
        "search": username
    })

    if data["status"] != "ok":
        return None

    result = data["data"]

    if not result:
        return None

    return result[0]["account_id"]


async def fetch_tank_stats(account_id: int, tank_id: int):
    data = await fetch("tanks/stats", {
        "account_id": account_id,
        "tank_id": tank_id,
        "fields": "all.battles,all.damage_dealt"
    })

    try:
        return data["data"][str(account_id)][0]["all"]
    except (KeyError, IndexError, TypeError):
        return None


async def get_tank_name(tank_id: int):
    data = await fetch("encyclopedia/vehicles", {
        "fields": "name"
    })

    tanks = data.get("data", {})

    tank = tanks.get(str(tank_id))
    if not tank:
        return None

    return tank["name"]


async def get_tank_by_name(name: str):
    data = await fetch("encyclopedia/vehicles", {
        "fields": "name"
    })

    if data["status"] != "ok":
        return None

    tanks = data["data"]

    name = name.strip().lower()

    for tank_id, tank in tanks.items():
        if tank["name"].lower() == name:
            return {
                "tank_id": int(tank_id),
                "tank_name": tank["name"]
            }

    return None
