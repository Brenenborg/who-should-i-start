"""
Weekly matchup preview.
Finds your current-week opponent on Sleeper and compares optimized
lineups so you can see if you're favored or an underdog, and why.
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


def get_nfl_state():
    return _fetch_json("https://api.sleeper.app/v1/state/nfl")


def build_matchup_preview(league_id, username, roster_positions, player_pool):
    state = get_nfl_state()
    week = state.get("week") or 1
    season_type = state.get("season_type", "regular")

    if season_type != "regular" or not state.get("week"):
        return {
            "available": False,
            "message": "Matchups aren't live yet - check back once your league's regular season starts.",
        }

    matchups = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/matchups/{week}")
    if not matchups:
        return {
            "available": False,
            "message": f"No matchup data found for week {week} yet.",
        }

    my_roster_id, my_players = lineup_optimizer.get_my_roster_info(league_id, username)
    if my_roster_id is None:
        return {"available": False, "message": "Could not find your team in this league."}

    my_matchup = next((m for m in matchups if m.get("roster_id") == my_roster_id), None)
    if not my_matchup:
        return {"available": False, "message": f"No matchup found for you in week {week}."}

    matchup_id = my_matchup.get("matchup_id")
    opponent_matchup = next(
        (m for m in matchups if m.get("matchup_id") == matchup_id and m.get("roster_id") != my_roster_id),
        None,
    )

    rosters = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/rosters")
    users = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/users")
    owner_by_roster = {r.get("roster_id"): r.get("owner_id") for r in rosters}
    name_by_owner = {u.get("user_id"): (u.get("display_name") or "Unnamed team") for u in users}

    my_name = name_by_owner.get(owner_by_roster.get(my_roster_id), "You")

    my_lineup = lineup_optimizer.optimize_lineup(my_players, roster_positions, player_pool, week)
    my_total = round(sum((p.get("per_game_avg") or p.get("points") or 0) for p in my_lineup["starters"]), 1)

    if not opponent_matchup:
        return {
            "available": True,
            "week": week,
            "my_name": my_name,
            "my_total": my_total,
            "my_lineup": my_lineup,
            "opponent_name": None,
            "opponent_total": None,
            "opponent_lineup": None,
            "favored": None,
            "bye_week": True,
        }

    opponent_roster_id = opponent_matchup.get("roster_id")
    opponent_name = name_by_owner.get(owner_by_roster.get(opponent_roster_id), "Opponent")
    opponent_players = opponent_matchup.get("players", [])
    opponent_lineup = lineup_optimizer.optimize_lineup(opponent_players, roster_positions, player_pool, week)
    opponent_total = round(sum((p.get("per_game_avg") or p.get("points") or 0) for p in opponent_lineup["starters"]), 1)

    return {
        "available": True,
        "week": week,
        "my_name": my_name,
        "my_total": my_total,
        "my_lineup": my_lineup,
        "opponent_name": opponent_name,
        "opponent_total": opponent_total,
        "opponent_lineup": opponent_lineup,
        "favored": my_total > opponent_total,
        "bye_week": False,
    }
