"""
Rankings engine.
Pulls real player stats and your league's own scoring rules from Sleeper,
then calculates a ranked list that accounts for Superflex scarcity.
"""

import urllib.request
import json
import os
import time

import bye_weeks

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

PLAYERS_CACHE_FILE = os.path.join(CACHE_DIR, "players.json")
RANKINGS_CACHE_FILE = os.path.join(CACHE_DIR, "rankings.json")
ONE_DAY_SECONDS = 24 * 60 * 60

# Rough, commonly-used split for how FLEX/SUPERFLEX slots tend to get filled.
# This is an approximation, not an exact science - it's what lets QBs rise
# properly in Superflex without needing a full draft simulation.
SUPERFLEX_SHARE = {"QB": 0.70, "RB": 0.15, "WR": 0.15, "TE": 0.00}
FLEX_SHARE = {"RB": 0.45, "WR": 0.45, "TE": 0.10}
WRRB_FLEX_SHARE = {"RB": 0.55, "WR": 0.45}
REC_FLEX_SHARE = {"WR": 0.70, "TE": 0.30}


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


def _load_cache(path, max_age_seconds):
    if not os.path.exists(path):
        return None
    if time.time() - os.path.getmtime(path) > max_age_seconds:
        return None
    with open(path, "r") as f:
        return json.load(f)


def _save_cache(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def get_all_players():
    """Full player directory (names, positions, teams). Cached - Sleeper
    asks that this heavy endpoint not be called often."""
    cached = _load_cache(PLAYERS_CACHE_FILE, max_age_seconds=ONE_DAY_SECONDS)
    if cached:
        return cached
    data = _fetch_json("https://api.sleeper.app/v1/players/nfl")
    _save_cache(PLAYERS_CACHE_FILE, data)
    return data


def get_league_settings(league_id):
    league = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}")
    return league.get("scoring_settings", {}), league.get("roster_positions", []), league


def get_season_stats(season):
    """Season-total stats for every player. Tries the given season first
    (in case games have been played), falls back to the prior season."""
    def _normalize(data):
        """Sleeper returns this as a list of per-player stat objects, not
        a dict keyed by player_id - convert it to a dict for easy lookup."""
        if isinstance(data, dict):
            return data
        normalized = {}
        for item in data:
            if not isinstance(item, dict):
                continue
            player_id = item.get("player_id")
            if not player_id:
                continue
            stats = item.get("stats", item)
            normalized[str(player_id)] = stats
        return normalized

    MEANINGFUL_STAT_KEYS = {
        "pass_yd", "pass_td", "rush_yd", "rush_td", "rec", "rec_yd", "rec_td",
        "pass_cmp", "pass_att", "rush_att",
    }

    def _has_real_data(normalized):
        """The current season exists as an object even before any games are
        played, sometimes with incidental non-zero metadata fields (bye
        week, IDs, etc). Only count it as real if actual game stats
        (yards, touchdowns, completions...) show up for a real number
        of players."""
        count = 0
        for stats in normalized.values():
            if not isinstance(stats, dict):
                continue
            if any(stats.get(k, 0) for k in MEANINGFUL_STAT_KEYS):
                count += 1
                if count > 20:
                    return True
        return False

    url = f"https://api.sleeper.com/stats/nfl/{season}?season_type=regular"
    try:
        data = _fetch_json(url)
        normalized = _normalize(data)
        if _has_real_data(normalized):
            return normalized, season
    except Exception:
        pass

    prior = str(int(season) - 1)
    url = f"https://api.sleeper.com/stats/nfl/{prior}?season_type=regular"
    data = _fetch_json(url)
    return _normalize(data), prior


def score_player(stats, scoring_settings):
    total = 0.0
    for stat_key, multiplier in scoring_settings.items():
        if stat_key in stats and isinstance(stats[stat_key], (int, float)):
            total += stats[stat_key] * multiplier
    return round(total, 2)


def get_weekly_points(season, scoring_settings, weeks=range(1, 19)):
    """Fetch each week's stats and score them, to see how much a player's
    output actually swings week to week (not just their season total)."""
    points_by_player = {}

    for week in weeks:
        url = f"https://api.sleeper.com/stats/nfl/{season}/{week}?season_type=regular"
        try:
            data = _fetch_json(url)
        except Exception:
            continue

        if isinstance(data, dict):
            week_stats = data
        else:
            week_stats = {}
            for item in data:
                if not isinstance(item, dict):
                    continue
                pid = item.get("player_id")
                if not pid:
                    continue
                week_stats[str(pid)] = item.get("stats", item)

        for pid, stats in week_stats.items():
            if not isinstance(stats, dict):
                continue
            pts = score_player(stats, scoring_settings)
            if pts > 0:
                points_by_player.setdefault(pid, []).append(pts)

    return points_by_player


def _recent_trend(weekly_points, season_avg):
    """The 'gut check': is a player's recent form a real trend, or just
    one weird week? Compares their last 3 games to their season average."""
    if len(weekly_points) < 4 or not season_avg:
        return None, None

    recent = weekly_points[-3:]
    recent_avg = sum(recent) / len(recent)
    diff_ratio = (recent_avg - season_avg) / season_avg

    if diff_ratio >= 0.15:
        label = "Trending up"
    elif diff_ratio <= -0.15:
        label = "Trending down"
    else:
        label = "Steady"

    reason = f"Last 3 games averaging {recent_avg:.1f} pts vs a {season_avg:.1f} season average"
    return label, reason


def _volatility_label(weekly_points):
    if len(weekly_points) < 3:
        return None
    mean = sum(weekly_points) / len(weekly_points)
    if mean <= 0:
        return None
    variance = sum((p - mean) ** 2 for p in weekly_points) / len(weekly_points)
    stdev = variance ** 0.5
    coefficient_of_variation = stdev / mean

    if coefficient_of_variation < 0.35:
        return "Consistent"
    elif coefficient_of_variation < 0.6:
        return "Moderate risk"
    else:
        return "Boom/bust"


def _starters_needed(roster_positions, num_teams):
    """How many players at each position your league actually needs
    starting each week, folding in a share of FLEX/SUPERFLEX."""
    base = {"QB": 0, "RB": 0, "WR": 0, "TE": 0}
    flex_count = 0
    superflex_count = 0
    wrrb_flex_count = 0
    rec_flex_count = 0

    for slot in roster_positions:
        if slot in base:
            base[slot] += 1
        elif slot == "FLEX":
            flex_count += 1
        elif slot in ("SUPER_FLEX", "SUPERFLEX"):
            superflex_count += 1
        elif slot == "WRRB_FLEX":
            wrrb_flex_count += 1
        elif slot in ("REC_FLEX", "WRTE_FLEX"):
            rec_flex_count += 1

    needed = dict(base)
    for pos, share in FLEX_SHARE.items():
        needed[pos] += flex_count * share
    for pos, share in SUPERFLEX_SHARE.items():
        needed[pos] += superflex_count * share
    for pos, share in WRRB_FLEX_SHARE.items():
        needed[pos] += wrrb_flex_count * share
    for pos, share in REC_FLEX_SHARE.items():
        needed[pos] += rec_flex_count * share

    return {pos: max(1, round(count * num_teams)) for pos, count in needed.items()}


def compute_rankings(league_id, season):
    scoring_settings, roster_positions, league = get_league_settings(league_id)
    num_teams = league.get("total_rosters", 12)
    all_players = get_all_players()
    season_stats, stats_season_used = get_season_stats(season)

    scored = []
    for player_id, stats in season_stats.items():
        meta = all_players.get(player_id)
        if not meta:
            continue
        position = meta.get("position")
        if position not in ("QB", "RB", "WR", "TE", "K", "DEF"):
            continue
        points = score_player(stats, scoring_settings)
        if points <= 0:
            continue
        name = f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
        scored.append(
            {
                "player_id": player_id,
                "name": name,
                "position": position,
                "team": meta.get("team") or "FA",
                "points": points,
                "injury_status": meta.get("injury_status"),
            }
        )

    needed = _starters_needed(roster_positions, num_teams)
    weekly_points_by_player = get_weekly_points(stats_season_used, scoring_settings)

    for p in scored:
        weekly = weekly_points_by_player.get(p["player_id"], [])
        p["consistency"] = _volatility_label(weekly)
        p["per_game_avg"] = round(sum(weekly) / len(weekly), 1) if weekly else None
        p["games_played"] = len(weekly)
        p["bye_week"] = bye_weeks.TEAM_BYE_WEEKS.get(p["team"])
        trend_label, trend_reason = _recent_trend(weekly, p["per_game_avg"])
        p["trend"] = trend_label
        p["trend_reason"] = trend_reason

    by_position = {}
    for p in scored:
        by_position.setdefault(p["position"], []).append(p)
    for pos_list in by_position.values():
        pos_list.sort(key=lambda p: p["points"], reverse=True)

    # Replacement level computed on a per-game basis, so the "why" reason
    # matches the same avg/game numbers used everywhere else in the app.
    by_position_avg = {}
    for p in scored:
        if p["per_game_avg"] is not None:
            by_position_avg.setdefault(p["position"], []).append(p)
    for pos_list in by_position_avg.values():
        pos_list.sort(key=lambda p: p["per_game_avg"], reverse=True)

    replacement_level_avg = {}
    for pos, players_at_pos in by_position_avg.items():
        idx = int(needed.get(pos, num_teams)) - 1
        idx = max(0, min(idx, len(players_at_pos) - 1))
        replacement_level_avg[pos] = players_at_pos[idx]["per_game_avg"] if players_at_pos else 0

    # Season-total replacement level still powers overall draft-value ranking,
    # since a full season of production is what matters most on draft day.
    replacement_level = {}
    for pos, players_at_pos in by_position.items():
        idx = int(needed.get(pos, num_teams)) - 1
        idx = max(0, min(idx, len(players_at_pos) - 1))
        replacement_level[pos] = players_at_pos[idx]["points"] if players_at_pos else 0

    for p in scored:
        p["value"] = round(p["points"] - replacement_level.get(p["position"], 0), 2)
        if p["per_game_avg"] is not None:
            value_per_game = round(p["per_game_avg"] - replacement_level_avg.get(p["position"], 0), 1)
            p["reason"] = (
                f"{value_per_game:+.1f} pts/gm vs. a replacement-level {p['position']} "
                f"in your league's format"
            )
        else:
            p["reason"] = "Not enough games played yet to compare"

    scored.sort(key=lambda p: p["value"], reverse=True)
    for i, p in enumerate(scored, start=1):
        p["rank"] = i

    return {
        "players": scored,
        "stats_season_used": stats_season_used,
        "computed_at": time.time(),
    }


def get_rankings(league_id, season, force_refresh=False):
    cache_file = os.path.join(CACHE_DIR, f"rankings_{league_id}.json")
    if not force_refresh:
        cached = _load_cache(cache_file, max_age_seconds=ONE_DAY_SECONDS)
        if cached:
            return cached
    result = compute_rankings(league_id, season)
    _save_cache(cache_file, result)
    return result
