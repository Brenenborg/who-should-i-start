"""
Waiver wire assistant.
Figures out who's actually available league-wide (not on anyone's
roster) and worth adding, plus which of your own players are the
weakest link and worth dropping.
"""

import urllib.request
import json

import lineup_optimizer


def _fetch_json(url, timeout=20):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_all_rostered_player_ids(league_id):
    rosters = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/rosters")
    ids = set()
    for r in rosters:
        for pid in (r.get("players") or []):
            ids.add(pid)
    return ids


def build_waiver_report(league_id, username, roster_positions, player_pool, top_n=15):
    rostered_ids = get_all_rostered_player_ids(league_id)

    free_agents = [p for p in player_pool if p.get("player_id") not in rostered_ids]
    free_agents.sort(key=lambda p: p.get("value", 0), reverse=True)
    pickups = free_agents[:top_n]

    pool_by_id = {p["player_id"]: p for p in player_pool}
    my_roster_id, my_player_ids = lineup_optimizer.get_my_roster_info(league_id, username)

    my_players = []
    for pid in my_player_ids:
        info = pool_by_id.get(pid)
        if info:
            my_players.append(dict(info))
        else:
            my_players.append(
                {"player_id": pid, "name": "Unknown player", "position": "?", "value": 0, "points": 0, "reason": ""}
            )

    lineup = lineup_optimizer.optimize_lineup(my_player_ids, roster_positions, player_pool)
    starting_ids = {p.get("player_id") for p in lineup["starters"] if p.get("player_id")}

    for p in my_players:
        p["starting"] = p.get("player_id") in starting_ids

    my_players.sort(key=lambda p: p.get("value", 0))

    return {
        "pickups": pickups,
        "your_roster": my_players,
    }
