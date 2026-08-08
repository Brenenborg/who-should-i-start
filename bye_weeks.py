"""
2026 NFL bye week schedule, and a way to check the current week.
"""

import urllib.request
import json

TEAM_BYE_WEEKS = {
    "CAR": 5, "KC": 5,
    "CIN": 6, "DET": 6, "MIA": 6, "MIN": 6,
    "BUF": 7, "JAX": 7, "LAC": 7, "WAS": 7,
    "HOU": 8, "NO": 8, "NYG": 8, "SF": 8,
    "PIT": 9, "TEN": 9,
    "CHI": 10, "DEN": 10, "PHI": 10, "TB": 10,
    "ATL": 11, "CLE": 11, "GB": 11, "LAR": 11, "NE": 11, "SEA": 11,
    "BAL": 13, "IND": 13, "LV": 13, "NYJ": 13,
    "ARI": 14, "DAL": 14,
}


def _fetch_json(url, timeout=15):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_bye_clusters(roster_players, min_cluster=2):
    """Groups your roster by bye week and flags any week where 2+ of your
    players share a bye - a real risk to spot on draft day, before it's
    too late to balance it out."""
    by_week = {}
    for p in roster_players:
        week = p.get("bye_week")
        if not week:
            continue
        by_week.setdefault(week, []).append(p)

    clusters = [
        {"week": week, "players": [{"name": p["name"], "position": p["position"]} for p in players]}
        for week, players in by_week.items()
        if len(players) >= min_cluster
    ]
    clusters.sort(key=lambda c: c["week"])
    return clusters


def get_current_nfl_week():
    """Returns the current NFL week number, or None if the regular
    season hasn't started yet."""
    try:
        state = _fetch_json("https://api.sleeper.app/v1/state/nfl")
    except Exception:
        return None
    if state.get("season_type") != "regular":
        return None
    return state.get("week")
