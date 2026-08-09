"""
League standings.
"""

import urllib.request
import json

import avatars


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


def get_standings(league_id):
    rosters = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/rosters")
    users = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/users")
    league = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}")
    playoff_teams = (league.get("settings") or {}).get("playoff_teams", 6)
    name_by_owner = {u.get("user_id"): (u.get("display_name") or "Unnamed team") for u in users}
    avatar_src_by_owner = avatars.avatar_source_by_user_from_list(users)

    standings = []
    for r in rosters:
        settings = r.get("settings") or {}
        fpts = settings.get("fpts", 0) + settings.get("fpts_decimal", 0) / 100
        fpts_against = settings.get("fpts_against", 0) + settings.get("fpts_against_decimal", 0) / 100
        standings.append(
            {
                "team_name": name_by_owner.get(r.get("owner_id"), "Unnamed team"),
                "avatar_url": avatars.local_avatar_url(avatar_src_by_owner.get(r.get("owner_id"))),
                "wins": settings.get("wins", 0),
                "losses": settings.get("losses", 0),
                "ties": settings.get("ties", 0),
                "points_for": round(fpts, 1),
                "points_against": round(fpts_against, 1),
            }
        )

    standings.sort(key=lambda t: (t["wins"], t["points_for"]), reverse=True)
    for i, t in enumerate(standings, start=1):
        t["place"] = i
    return {"standings": standings, "playoff_teams": playoff_teams}
