def calculate_session_stats(current, start):
    session_battles = current["battles"] - start["battles"]

    if session_battles <= 0:
        return None

    session_damage = current["damage_dealt"] - start["damage_dealt"]
    avg_damage = session_damage / session_battles

    return {
        "battles": session_battles,
        "avg_damage": round(avg_damage, 2),
    }
