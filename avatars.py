"""
Team avatars.
Resolves each league member's avatar (their custom team avatar if they've
set one, otherwise their personal Sleeper profile picture) and caches the
actual image file locally the first time it's requested - so avatars show
up fast around the app without hotlinking Sleeper's CDN on every load.
"""

import urllib.request
import json
import os
import hashlib

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache", "avatars")
INDEX_FILE = os.path.join(CACHE_DIR, "_index.json")
os.makedirs(CACHE_DIR, exist_ok=True)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

EXT_BY_CONTENT_TYPE = {"image/webp": "webp", "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif"}


def _fetch_json(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_image_bytes(url, timeout=20):
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        content_type = resp.headers.get_content_type() or "image/webp"
        return resp.read(), content_type


def _load_index():
    if not os.path.exists(INDEX_FILE):
        return {}
    try:
        with open(INDEX_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_index(index):
    with open(INDEX_FILE, "w") as f:
        json.dump(index, f)


def avatar_source_by_user(league_id):
    """Fetches league members fresh and returns {user_id: source_url}."""
    users = _fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/users")
    return avatar_source_by_user_from_list(users)


def avatar_source_by_user_from_list(users):
    """Same as avatar_source_by_user, but works off a users list you've
    already fetched - saves a duplicate API call when the caller already
    needed /users for team names anyway."""
    result = {}
    for u in users:
        meta = u.get("metadata") or {}
        raw = meta.get("avatar") or u.get("avatar")
        user_id = u.get("user_id")
        if not raw:
            result[user_id] = None
        elif isinstance(raw, str) and raw.startswith("http"):
            result[user_id] = raw
        else:
            result[user_id] = f"https://sleepercdn.com/avatars/thumbs/{raw}"
    return result


def local_avatar_url(source_url):
    """Registers a Sleeper avatar source URL under a stable local key and
    returns this app's own /api/avatar/<key> URL for it - or None if
    there's no avatar to show."""
    if not source_url:
        return None
    key = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:16]
    index = _load_index()
    if index.get(key) != source_url:
        index[key] = source_url
        _save_index(index)
    return f"/api/avatar/{key}"


def get_cached_avatar_path(key):
    """Downloads and caches the image for this key the first time it's
    requested; every request after that is served straight from disk.
    Returns (file_path, content_type), or (None, None) if unavailable."""
    index = _load_index()
    source_url = index.get(key)
    if not source_url:
        return None, None

    for content_type, ext in EXT_BY_CONTENT_TYPE.items():
        candidate = os.path.join(CACHE_DIR, f"{key}.{ext}")
        if os.path.exists(candidate):
            return candidate, content_type

    try:
        data, content_type = _fetch_image_bytes(source_url)
    except Exception:
        return None, None

    ext = EXT_BY_CONTENT_TYPE.get(content_type, "img")
    path = os.path.join(CACHE_DIR, f"{key}.{ext}")
    with open(path, "wb") as f:
        f.write(data)
    return path, content_type
