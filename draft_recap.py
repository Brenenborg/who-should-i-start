"""
Draft recap - shows every pick made in your league's draft, in order.
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


def get_draft_recap(league_id, player_pool=None):
    drafts = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/drafts")
    if not drafts:
        return {"available": False, "message": "No draft found for this league yet."}
    draft_id = drafts[0]["draft_id"]

    picks = _fetch_json(f"https://api.sleeper.app/v1/draft/{draft_id}/picks")
    if not picks:
        return {"available": False, "message": "The draft hasn't started yet - picks will show up here once it begins."}

    users = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/users")
    name_by_owner = {u.get("user_id"): (u.get("display_name") or "Unnamed team") for u in users}
    avatar_src_by_owner = avatars.avatar_source_by_user_from_list(users)

    value_by_name = {}
    if player_pool:
        for p in player_pool:
            value_by_name[p["name"].lower()] = p.get("value", 0) or 0

    recap = []
    team_totals = {}
    team_avatars = {}
    for pick in picks:
        meta = pick.get("metadata") or {}
        player_name = f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip() or "Unknown"
        owner_id = pick.get("picked_by")
        team_name = name_by_owner.get(owner_id, "Bot pick")
        avatar_url = avatars.local_avatar_url(avatar_src_by_owner.get(owner_id))
        team_avatars[team_name] = avatar_url
        value = value_by_name.get(player_name.lower(), 0)
        recap.append(
            {
                "pick_no": pick.get("pick_no"),
                "round": pick.get("round"),
                "team_name": team_name,
                "avatar_url": avatar_url,
                "player_name": player_name,
                "position": meta.get("position", ""),
                "nfl_team": meta.get("team", ""),
                "value": value,
            }
        )
        team_totals[team_name] = team_totals.get(team_name, 0) + value

    recap.sort(key=lambda p: p["pick_no"] or 0)

    grades = _compute_grades(team_totals, team_avatars)
    return {"available": True, "picks": recap, "grades": grades}


def _compute_grades(team_totals, team_avatars=None):
    team_avatars = team_avatars or {}
    ranked = sorted(team_totals.items(), key=lambda kv: kv[1], reverse=True)
    n = len(ranked)
    if n == 0:
        return []
    grades = []
    labels = ["A+", "A", "B+", "B", "C", "D"]
    for i, (team_name, total) in enumerate(ranked):
        bucket = min(int((i / n) * len(labels)), len(labels) - 1)
        grades.append({
            "team_name": team_name,
            "avatar_url": team_avatars.get(team_name),
            "total_value": round(total, 1),
            "grade": labels[bucket],
        })
    return grades
