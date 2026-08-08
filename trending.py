"""
Trending players - who's being added across Sleeper leagues right now.
Uses Sleeper's official trending endpoint, not scraped/guessed data.
"""

import urllib.request
import json


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


def get_trending_adds(all_players, limit=10):
    url = f"https://api.sleeper.app/v1/players/nfl/trending/add?lookback_hours=48&limit={limit * 2}"
    try:
        data = _fetch_json(url)
    except Exception:
        return []

    trending = []
    for item in data:
        pid = item.get("player_id")
        meta = all_players.get(pid)
        if not meta:
            continue
        position = meta.get("position")
        if position not in ("QB", "RB", "WR", "TE", "K", "DEF"):
            continue
        name = f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
        trending.append(
            {
                "name": name,
                "position": position,
                "team": meta.get("team") or "FA",
                "add_count": item.get("count", 0),
            }
        )
        if len(trending) >= limit:
            break

    return trending
