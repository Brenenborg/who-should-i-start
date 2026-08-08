"""
League profiles.
Instead of one shared setting, this stores a list of leagues (each with
its own League ID, username, and season). Each browser/device picks
which one it's viewing on its own (stored in that browser only), so
switching leagues on one device never affects anyone else.
"""

import json
import os
import uuid

LEAGUES_FILE = os.path.join(os.path.dirname(__file__), "cache", "leagues.json")
LEGACY_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "cache", "config.json")

DEFAULT_PROFILE = {
    "label": "My League",
    "league_id": "1389030413707534336",
    "username": "brenenborg",
    "season": "2026",
}


def _migrate_legacy_config():
    """If this Mac still has the old single-config.json from before
    multi-league support, bring it in as the first saved league."""
    if os.path.exists(LEGACY_CONFIG_FILE) and not os.path.exists(LEAGUES_FILE):
        try:
            with open(LEGACY_CONFIG_FILE, "r") as f:
                old = json.load(f)
        except Exception:
            old = {}
        profile = dict(DEFAULT_PROFILE)
        profile.update(old)
        profile["id"] = "default"
        profile["label"] = "My League"
        save_leagues([profile])


def load_leagues():
    _migrate_legacy_config()
    if not os.path.exists(LEAGUES_FILE):
        profile = dict(DEFAULT_PROFILE)
        profile["id"] = "default"
        save_leagues([profile])
    with open(LEAGUES_FILE, "r") as f:
        return json.load(f)


def save_leagues(leagues):
    os.makedirs(os.path.dirname(LEAGUES_FILE), exist_ok=True)
    with open(LEAGUES_FILE, "w") as f:
        json.dump(leagues, f)


def get_profile(profile_id):
    """Looks up a specific saved league by id. Falls back to the first
    saved league if no id given or it isn't found, so the app always
    has something sensible to show."""
    leagues = load_leagues()
    if not leagues:
        return None
    if profile_id:
        for p in leagues:
            if p["id"] == profile_id:
                return p
    return leagues[0]


def add_or_update_profile(data):
    leagues = load_leagues()
    profile_id = data.get("id")

    if profile_id:
        for i, p in enumerate(leagues):
            if p["id"] == profile_id:
                leagues[i] = {**p, **data}
                save_leagues(leagues)
                return leagues[i]

    new_profile = {
        "id": uuid.uuid4().hex[:8],
        "label": data.get("label") or "My League",
        "league_id": data.get("league_id", ""),
        "username": data.get("username", ""),
        "season": data.get("season") or "2026",
    }
    leagues.append(new_profile)
    save_leagues(leagues)
    return new_profile


def delete_profile(profile_id):
    leagues = load_leagues()
    leagues = [p for p in leagues if p["id"] != profile_id]
    save_leagues(leagues)
    return leagues
