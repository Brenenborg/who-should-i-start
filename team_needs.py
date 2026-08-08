"""
Team needs tracker.
Looks at what you've drafted so far and compares it to your league's
actual roster requirements, so you know what to prioritize next.
"""

import urllib.request
import json
from collections import Counter

FIXED_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF"}


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


def get_my_drafted_positions(league_id, username):
    user = _fetch_json(f"https://api.sleeper.app/v1/user/{username}")
    user_id = user["user_id"]

    drafts = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/drafts")
    if not drafts:
        return []
    draft_id = drafts[0]["draft_id"]

    picks = _fetch_json(f"https://api.sleeper.app/v1/draft/{draft_id}/picks")
    positions = []
    for pick in picks:
        if pick.get("picked_by") == user_id:
            meta = pick.get("metadata") or {}
            pos = meta.get("position")
            if pos:
                positions.append(pos)
    return positions


def build_needs_report(roster_positions, drafted_positions):
    base_needed = {pos: 0 for pos in FIXED_POSITIONS}
    flex_slot_count = 0

    for slot in roster_positions:
        if slot in base_needed:
            base_needed[slot] += 1
        elif slot in ("FLEX", "SUPER_FLEX", "SUPERFLEX", "WRRB_FLEX", "REC_FLEX", "WRTE_FLEX"):
            flex_slot_count += 1

    drafted_counts = Counter(drafted_positions)

    needs = []
    for pos in ("QB", "RB", "WR", "TE", "K", "DEF"):
        needed = base_needed.get(pos, 0)
        have = drafted_counts.get(pos, 0)
        needs.append(
            {
                "position": pos,
                "needed": needed,
                "have": have,
                "remaining": max(0, needed - have),
            }
        )

    return {
        "needs": needs,
        "flex_slots": flex_slot_count,
        "total_drafted": len(drafted_positions),
    }
