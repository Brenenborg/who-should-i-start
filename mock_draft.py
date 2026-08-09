"""
Mock draft projector.
Simulates the rest of your league's draft, pick by pick, so you can see who's
realistically likely to be available each time it's your turn. Every team
(including yours) is assumed to take the best remaining value for a slot
they still genuinely need - real human drafters will deviate, so treat this
as a planning tool for targets, not a guarantee.

If the real draft has already started, already-made picks are pulled from
Sleeper and used to seed every team's roster before the simulation continues
for the picks that haven't happened yet.
"""

import urllib.request
import urllib.error
import json
import re

import rankings_engine

# Which roster slot types a position is eligible to start in, ordered by
# specificity - a QB should fill an open "QB" slot before eating a
# superflex slot that an RB/WR/TE couldn't otherwise use.
QUALIFYING_SLOTS = {
    "QB": ["QB", "SUPER_FLEX", "SUPERFLEX"],
    "RB": ["RB", "FLEX", "WRRB_FLEX", "SUPER_FLEX", "SUPERFLEX"],
    "WR": ["WR", "FLEX", "WRRB_FLEX", "REC_FLEX", "WRTE_FLEX", "SUPER_FLEX", "SUPERFLEX"],
    "TE": ["TE", "FLEX", "REC_FLEX", "WRTE_FLEX", "SUPER_FLEX", "SUPERFLEX"],
    "K": ["K"],
    "DEF": ["DEF"],
}

# How much we discount a player's value when a team has no open starter
# slot left for that position (i.e. this pick would just be a bench stash).
# Keeps teams from unrealistically hoarding one position round after round.
BENCH_ONLY_PENALTY_FRACTION = 0.12

# Only the realistic top of the remaining pool needs to be scanned each pick -
# keeps a 12-16 round, 10-14 team simulation fast without changing the outcome.
SCAN_WINDOW = 40


def _fetch_json(url, timeout=20):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise urllib.error.HTTPError(url, e.code, f"{e.reason} - GET {url}", e.headers, e.fp)


def _normalize_name(name):
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r"[.'\-]", "", name)
    name = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _get_real_picks(league_id):
    """Picks already made in the actual Sleeper draft, if it's been created/
    started. Empty list if the draft hasn't begun yet - totally normal for
    pre-draft planning."""
    drafts = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/drafts")
    if not drafts:
        return []
    draft_id = drafts[0]["draft_id"]
    picks = _fetch_json(f"https://api.sleeper.app/v1/draft/{draft_id}/picks")
    result = []
    for pick in picks:
        meta = pick.get("metadata") or {}
        full_name = f"{meta.get('first_name', '')} {meta.get('last_name', '')}".strip()
        if not pick.get("pick_no"):
            continue
        result.append(
            {
                "pick_no": pick["pick_no"],
                "position": meta.get("position"),
                "normalized_name": _normalize_name(full_name),
            }
        )
    result.sort(key=lambda p: p["pick_no"])
    return result


def _detect_draft_slot(league_id, username):
    """Best-effort auto-detect of which draft slot belongs to this user.
    Only works once the commissioner has set/randomized the draft order in
    Sleeper - returns None otherwise so the app can just ask."""
    if not username:
        return None
    try:
        user = _fetch_json(f"https://api.sleeper.app/v1/user/{username}")
        user_id = user.get("user_id")
        if not user_id:
            return None
        drafts = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/drafts")
        if not drafts:
            return None
        draft = _fetch_json(f"https://api.sleeper.app/v1/draft/{drafts[0]['draft_id']}")
        draft_order = draft.get("draft_order") or {}
        slot = draft_order.get(user_id)
        return int(slot) if slot else None
    except Exception:
        return None


def _pick_position(pick_no, num_teams):
    """Standard snake draft math: which round, and which draft slot (1-based)
    is on the clock for a given overall pick number."""
    rnd = (pick_no - 1) // num_teams + 1
    pos_in_round = (pick_no - 1) % num_teams + 1
    slot = pos_in_round if rnd % 2 == 1 else (num_teams - pos_in_round + 1)
    return rnd, slot


def _team_open_slots_template(roster_positions):
    counts = {}
    for slot in roster_positions:
        counts[slot] = counts.get(slot, 0) + 1
    return counts


def _fill_slot(open_slots, position):
    """Assigns a drafted player into the most specific open starter slot
    they qualify for, falling back to bench. Returns True if it filled a
    starter slot (vs. just going to the bench)."""
    for slot_type in QUALIFYING_SLOTS.get(position, []):
        if open_slots.get(slot_type, 0) > 0:
            open_slots[slot_type] -= 1
            return True
    if open_slots.get("BN", 0) > 0:
        open_slots["BN"] -= 1
        return False
    return False


def _adjusted_value(player, open_slots):
    value = player.get("value") or 0
    has_starter_slot = any(
        open_slots.get(slot_type, 0) > 0 for slot_type in QUALIFYING_SLOTS.get(player["position"], [])
    )
    return value if has_starter_slot else value * (1 - BENCH_ONLY_PENALTY_FRACTION)


def _slim(p):
    return {"name": p["name"], "position": p["position"], "team": p["team"], "value": p["value"]}


FIXED_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")


def _roster_targets(roster_positions):
    """How many starters your league requires at each fixed position,
    plus how many flex-type slots (FLEX/SUPERFLEX/etc.) exist separately -
    those can go to more than one position, so they're reported on their
    own rather than force-split across positions."""
    base = {pos: 0 for pos in FIXED_POSITIONS}
    flex_count = 0
    for slot in roster_positions:
        if slot in base:
            base[slot] += 1
        elif slot in ("FLEX", "SUPER_FLEX", "SUPERFLEX", "WRRB_FLEX", "REC_FLEX", "WRTE_FLEX"):
            flex_count += 1
    return base, flex_count


def _get_total_rounds(league_id, roster_positions):
    """The real round count lives on the DRAFT object (settings.rounds),
    not the league object - league settings has no such field. Falls back
    to counting roster slots only if the draft can't be found yet."""
    try:
        drafts = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/drafts")
        if drafts:
            draft = _fetch_json(f"https://api.sleeper.app/v1/draft/{drafts[0]['draft_id']}")
            rounds = (draft.get("settings") or {}).get("rounds")
            if rounds:
                return int(rounds)
    except Exception:
        pass
    return len(roster_positions) or 15


def get_draft_meta(league_id, username=None):
    """Fast metadata call - just enough to build the setup screen (slot input
    + one strategy row per round + a live position tally) without running
    the full simulation."""
    _, roster_positions, league = rankings_engine.get_league_settings(league_id)
    num_teams = league.get("total_rosters", 12)
    total_rounds = _get_total_rounds(league_id, roster_positions)
    detected_slot = _detect_draft_slot(league_id, username)
    roster_targets, flex_slots = _roster_targets(roster_positions)
    return {
        "num_teams": num_teams,
        "total_rounds": total_rounds,
        "detected_slot": detected_slot,
        "roster_targets": roster_targets,
        "flex_slots": flex_slots,
    }


def simulate_mock_draft(league_id, season, my_slot=None, username=None, strategy=None):
    """strategy: optional dict of {round_number: position}. For any round
    listed, YOUR pick in the simulation is forced to that position (still
    picking the best value player at that position) instead of the default
    best-value-for-a-need-slot logic. Rounds not listed fall back to that
    default, same as everyone else's picks."""
    strategy = strategy or {}
    scoring_settings, roster_positions, league = rankings_engine.get_league_settings(league_id)
    num_teams = league.get("total_rosters", 12)
    total_rounds = _get_total_rounds(league_id, roster_positions)
    total_picks = num_teams * total_rounds

    slot_detected = False
    if not my_slot:
        detected = _detect_draft_slot(league_id, username)
        if detected:
            my_slot = detected
            slot_detected = True

    if not my_slot:
        return {
            "needs_slot": True,
            "num_teams": num_teams,
            "slot_detected": False,
        }

    my_slot = max(1, min(int(my_slot), num_teams))

    rankings_result = rankings_engine.get_rankings(league_id, season)
    rankings = rankings_result["players"]
    pool = [dict(p) for p in rankings if p["position"] in QUALIFYING_SLOTS]
    pool.sort(key=lambda p: p["value"], reverse=True)

    real_picks = _get_real_picks(league_id)
    drafted_names = {rp["normalized_name"] for rp in real_picks if rp["normalized_name"]}
    pool = [p for p in pool if _normalize_name(p["name"]) not in drafted_names]

    team_slots = {slot: _team_open_slots_template(roster_positions) for slot in range(1, num_teams + 1)}
    for rp in real_picks:
        if rp["pick_no"] > total_picks or not rp.get("position"):
            continue
        _, slot = _pick_position(rp["pick_no"], num_teams)
        _fill_slot(team_slots.get(slot, {}), rp["position"])

    start_pick = len(real_picks) + 1
    your_picks = []

    for pick_no in range(start_pick, total_picks + 1):
        if not pool:
            break
        rnd, slot = _pick_position(pick_no, num_teams)
        open_slots = team_slots[slot]

        is_you = slot == my_slot
        board_top_overall = [_slim(p) for p in pool[:8]] if is_you else None
        board_by_position = None
        if is_you:
            board_by_position = {
                pos: [_slim(p) for p in pool if p["position"] == pos][:5] for pos in ("QB", "RB", "WR", "TE")
            }

        window = pool[: min(SCAN_WINDOW, len(pool))]
        target_pos = strategy.get(rnd) if is_you else None
        if target_pos:
            candidates = [p for p in pool if p["position"] == target_pos]
            if not candidates:
                candidates = window  # nobody left at the targeted position - fall back to best value
        else:
            candidates = window

        best, best_score = None, None
        for p in candidates:
            score = _adjusted_value(p, open_slots)
            if best_score is None or score > best_score:
                best_score, best = score, p
        picked = best
        pool.remove(picked)
        _fill_slot(open_slots, picked["position"])

        if is_you:
            your_picks.append(
                {
                    "pick_no": pick_no,
                    "round": rnd,
                    "projected_pick": _slim(picked),
                    "targeted_position": target_pos if target_pos else None,
                    "board_top_overall": board_top_overall,
                    "board_by_position": board_by_position,
                }
            )

    return {
        "num_teams": num_teams,
        "total_rounds": total_rounds,
        "my_slot": my_slot,
        "slot_detected": slot_detected,
        "picks_already_made": len(real_picks),
        "your_picks": your_picks,
        "points_source": rankings_result.get("points_source"),
        "points_season": rankings_result.get("stats_season_used"),
    }
