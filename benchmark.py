"""
How you compare - benchmarks your roster's total value and per-position
strength against the league average.
"""

import urllib.request
import json


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


def build_benchmark(league_id, my_roster_id, player_pool):
    rosters = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/rosters")
    pool_by_id = {p["player_id"]: p for p in player_pool}

    team_totals = []
    my_position_totals = {}
    league_position_totals = {}

    for r in rosters:
        total = 0
        position_totals = {}
        for pid in (r.get("players") or []):
            info = pool_by_id.get(pid)
            if not info:
                continue
            value = info.get("value", 0) or 0
            total += value
            pos = info.get("position")
            position_totals[pos] = position_totals.get(pos, 0) + value

        team_totals.append(total)
        is_me = r.get("roster_id") == my_roster_id
        if is_me:
            my_position_totals = position_totals
        for pos, val in position_totals.items():
            league_position_totals.setdefault(pos, []).append(val)

    if not team_totals:
        return {"available": False, "message": "No rosters found yet."}

    league_avg = sum(team_totals) / len(team_totals)
    my_total = next(
        (
            sum((pool_by_id.get(pid, {}).get("value", 0) or 0) for pid in r.get("players") or [])
            for r in rosters
            if r.get("roster_id") == my_roster_id
        ),
        0,
    )

    position_comparison = []
    for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
        league_vals = league_position_totals.get(pos, [])
        league_pos_avg = sum(league_vals) / len(league_vals) if league_vals else 0
        position_comparison.append(
            {
                "position": pos,
                "your_value": round(my_position_totals.get(pos, 0), 1),
                "league_avg": round(league_pos_avg, 1),
            }
        )

    return {
        "available": True,
        "your_total": round(my_total, 1),
        "league_avg_total": round(league_avg, 1),
        "position_comparison": position_comparison,
    }
