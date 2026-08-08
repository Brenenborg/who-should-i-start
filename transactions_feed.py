"""
Recent league transactions - trades and waiver/free-agent moves across
the whole league, not just your team.
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


def get_recent_transactions(league_id, current_week, all_players, max_items=20):
    if not current_week:
        current_week = 1

    users = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/users")
    rosters = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/rosters")
    name_by_owner = {u.get("user_id"): (u.get("display_name") or "Unnamed team") for u in users}
    owner_by_roster = {r.get("roster_id"): r.get("owner_id") for r in rosters}

    def team_name(roster_id):
        return name_by_owner.get(owner_by_roster.get(roster_id), "Unknown team")

    def player_name(pid):
        meta = all_players.get(pid)
        if not meta:
            return pid
        return f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()

    items = []
    weeks_to_check = range(max(1, current_week - 1), current_week + 1)
    for week in weeks_to_check:
        try:
            txns = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/transactions/{week}")
        except Exception:
            continue
        for t in txns:
            if t.get("status") != "complete":
                continue
            t_type = t.get("type")
            roster_ids = t.get("roster_ids") or []
            adds = t.get("adds") or {}
            drops = t.get("drops") or {}

            if t_type == "trade":
                teams = ", ".join(team_name(rid) for rid in roster_ids)
                players_moved = ", ".join(player_name(pid) for pid in list(adds.keys())) or "players"
                summary = f"Trade between {teams}: {players_moved}"
            else:
                add_names = [player_name(pid) for pid, rid in adds.items()]
                drop_names = [player_name(pid) for pid, rid in drops.items()]
                team = team_name(roster_ids[0]) if roster_ids else "A team"
                parts = []
                if add_names:
                    parts.append(f"added {', '.join(add_names)}")
                if drop_names:
                    parts.append(f"dropped {', '.join(drop_names)}")
                summary = f"{team} {' and '.join(parts)}" if parts else f"{team} made a roster move"

            items.append(
                {
                    "type": t_type,
                    "summary": summary,
                    "created": t.get("created", 0),
                }
            )

    items.sort(key=lambda x: x["created"], reverse=True)
    return items[:max_items]
