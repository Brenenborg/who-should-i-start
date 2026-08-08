"""
Lineup optimizer.
Finds your team on Sleeper and figures out the highest-scoring lineup
that fits your league's exact roster slots.
"""

import urllib.request
import json


def _fetch_json(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_my_roster(league_id, username):
    user = _fetch_json(f"https://api.sleeper.app/v1/user/{username}")
    user_id = user["user_id"]

    rosters = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/rosters")
    for roster in rosters:
        if roster.get("owner_id") == user_id:
            return roster.get("players", [])
    return []


def get_my_roster_info(league_id, username):
    """Same as get_my_roster, but also returns your roster_id - needed to
    find your opponent in the weekly matchups."""
    user = _fetch_json(f"https://api.sleeper.app/v1/user/{username}")
    user_id = user["user_id"]

    rosters = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/rosters")
    for roster in rosters:
        if roster.get("owner_id") == user_id:
            return roster.get("roster_id"), roster.get("players", [])
    return None, []


# Which positions are allowed to fill each type of roster slot
SLOT_ELIGIBILITY = {
    "QB": {"QB"},
    "RB": {"RB"},
    "WR": {"WR"},
    "TE": {"TE"},
    "K": {"K"},
    "DEF": {"DEF"},
    "FLEX": {"RB", "WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"},
    "SUPERFLEX": {"QB", "RB", "WR", "TE"},
    "WRRB_FLEX": {"RB", "WR"},
    "REC_FLEX": {"WR", "TE"},
    "WRTE_FLEX": {"WR", "TE"},
}

SLOT_FILL_ORDER = [
    "QB", "RB", "WR", "TE", "K", "DEF",
    "WRRB_FLEX", "REC_FLEX", "WRTE_FLEX", "FLEX", "SUPER_FLEX", "SUPERFLEX",
]


def optimize_lineup(roster_player_ids, roster_positions, player_pool, current_week=None):
    """
    roster_player_ids: list of player_id strings on your team
    roster_positions: your league's slot list (from Sleeper), may include BN/IR
    player_pool: list of scored player dicts from rankings_engine (has player_id, points, position, injury_status)
    current_week: this week's NFL week number, used to skip players on bye
    """
    pool_by_id = {p["player_id"]: p for p in player_pool}

    my_players = []
    for pid in roster_player_ids:
        info = pool_by_id.get(pid)
        if info:
            my_players.append(dict(info))
        else:
            my_players.append(
                {"player_id": pid, "name": "Unknown player", "position": "UNKNOWN", "points": 0, "injury_status": None}
            )

    starting_slots = [s for s in roster_positions if s in SLOT_ELIGIBILITY]

    def _rank_value(player):
        return player.get("per_game_avg") if player.get("per_game_avg") is not None else player.get("points", 0)

    available = sorted(my_players, key=_rank_value, reverse=True)
    lineup = []
    used_ids = set()

    ordered_slots = sorted(
        starting_slots,
        key=lambda s: SLOT_FILL_ORDER.index(s) if s in SLOT_FILL_ORDER else 99,
    )

    for slot in ordered_slots:
        eligible_positions = SLOT_ELIGIBILITY[slot]
        pick = None
        for player in available:
            if player["player_id"] in used_ids:
                continue
            if player["position"] not in eligible_positions:
                continue
            if player.get("injury_status") in ("Out", "IR", "Suspended"):
                continue
            if current_week and player.get("bye_week") == current_week:
                continue
            pick = player
            break
        if pick:
            lineup.append({"slot": slot, **pick})
            used_ids.add(pick["player_id"])
        else:
            lineup.append({"slot": slot, "name": "No eligible player available", "points": 0})

    bench = [p for p in my_players if p["player_id"] not in used_ids]

    return {"starters": lineup, "bench": bench}
