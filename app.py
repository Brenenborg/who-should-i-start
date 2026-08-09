"""
Fantasy Draft Helper - local app
Auto-generates player rankings from real stats + your league's scoring
rules, filters out drafted players, and helps you set your best lineup.
Supports multiple saved leagues - each browser picks its own.
"""

from flask import Flask, jsonify, render_template, request
import urllib.request
import json
import os
import re

import rankings_engine
import lineup_optimizer
import matchup_preview
import waiver_assistant
import team_needs
import news_feed
import bye_weeks
import standings
import draft_recap
import defense_strength
import transactions_feed
import benchmark
import leagues
import trending
import schedule
import mock_draft

app = Flask(__name__)


def current_profile():
    """Every request tells us which saved league it wants via ?profile=<id>.
    If missing, we fall back to the first saved league."""
    profile_id = request.args.get("profile")
    return leagues.get_profile(profile_id)


def get_enriched_rankings(profile):
    """Rankings plus this week's real opponent, matchup difficulty, and
    weather - attached fresh each request since the schedule/weather
    changes more often than the daily rankings cache."""
    result = rankings_engine.get_rankings(profile["league_id"], profile["season"])
    try:
        current_week = bye_weeks.get_current_nfl_week()
        if current_week:
            schedule_data = schedule.get_week_schedule(profile["season"], current_week)
            defense_rankings = defense_strength.get_defense_rankings(result["players"])
            defense_strength.attach_matchup_info(result["players"], schedule_data, defense_rankings)
    except Exception:
        pass
    return result


def manual_players_file(league_id):
    return os.path.join(os.path.dirname(__file__), "cache", f"manual_players_{league_id}.json")


def watchlist_file(league_id):
    return os.path.join(os.path.dirname(__file__), "cache", f"watchlist_{league_id}.json")


def load_watchlist(league_id):
    path = watchlist_file(league_id)
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_watchlist(league_id, names):
    path = watchlist_file(league_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(names, f)


def load_manual_players(league_id):
    path = manual_players_file(league_id)
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def save_manual_players(league_id, players):
    path = manual_players_file(league_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(players, f)


def normalize_name(name):
    if not name:
        return ""
    name = name.lower()
    name = re.sub(r"[.'\-]", "", name)
    name = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def fetch_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def get_draft_id(league_id):
    drafts = fetch_json(f"https://api.sleeper.app/v1/league/{league_id}/drafts")
    if not drafts:
        return None
    return drafts[0]["draft_id"]


def get_drafted_names(league_id):
    draft_id = get_draft_id(league_id)
    if not draft_id:
        return set()
    picks = fetch_json(f"https://api.sleeper.app/v1/draft/{draft_id}/picks")
    drafted = set()
    for pick in picks:
        meta = pick.get("metadata") or {}
        full = normalize_name(f"{meta.get('first_name', '')} {meta.get('last_name', '')}")
        if full:
            drafted.add(full)
    return drafted


@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# League profile management
# ---------------------------------------------------------------------------

@app.route("/api/leagues", methods=["GET"])
def api_get_leagues():
    return jsonify({"leagues": leagues.load_leagues()})


@app.route("/api/leagues", methods=["POST"])
def api_save_league():
    data = request.get_json(force=True)
    if not data.get("league_id") or not data.get("username"):
        return jsonify({"error": "League ID and username are required."}), 400
    profile = leagues.add_or_update_profile(data)
    return jsonify({"ok": True, "profile": profile})


@app.route("/api/leagues/<profile_id>", methods=["DELETE"])
def api_delete_league(profile_id):
    remaining = leagues.delete_profile(profile_id)
    return jsonify({"ok": True, "leagues": remaining})


# ---------------------------------------------------------------------------
# Draft / rankings
# ---------------------------------------------------------------------------

@app.route("/api/available")
def api_available():
    profile = current_profile()
    try:
        drafted = get_drafted_names(profile["league_id"])
        drafted_error = None
    except Exception as e:
        drafted = set()
        drafted_error = str(e)

    try:
        result = get_enriched_rankings(profile)
    except Exception as e:
        return jsonify({"error": f"Could not build rankings: {e}"}), 500

    players = list(result["players"])

    for manual in load_manual_players(profile["league_id"]):
        players.append(
            {
                "player_id": f"manual-{normalize_name(manual['name'])}",
                "name": manual["name"],
                "position": manual["position"],
                "team": manual.get("team", ""),
                "points": None,
                "value": None,
                "rank": None,
                "notes": manual.get("notes", "Manually added"),
                "manual": True,
            }
        )

    available = [p for p in players if normalize_name(p["name"]) not in drafted]

    watchlist = set(load_watchlist(profile["league_id"]))
    for p in available:
        p["watchlisted"] = p["name"] in watchlist

    return jsonify(
        {
            "available": available,
            "drafted_count": len(drafted),
            "total_count": len(players),
            "stats_season_used": result.get("stats_season_used"),
            "points_source": result.get("points_source"),
            "drafted_fetch_error": drafted_error,
        }
    )


@app.route("/api/watchlist/toggle", methods=["POST"])
def api_watchlist_toggle():
    profile = current_profile()
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Player name required"}), 400
    watchlist = load_watchlist(profile["league_id"])
    if name in watchlist:
        watchlist.remove(name)
    else:
        watchlist.append(name)
    save_watchlist(profile["league_id"], watchlist)
    return jsonify({"ok": True, "watchlisted": name in watchlist})


@app.route("/api/add-player", methods=["POST"])
def api_add_player():
    profile = current_profile()
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    position = (data.get("position") or "").strip().upper()
    team = (data.get("team") or "").strip()
    notes = (data.get("notes") or "").strip()

    if not name or not position:
        return jsonify({"error": "Name and position are required."}), 400

    manual = load_manual_players(profile["league_id"])
    manual.append({"name": name, "position": position, "team": team, "notes": notes})
    save_manual_players(profile["league_id"], manual)
    return jsonify({"ok": True})


@app.route("/api/standings")
def api_standings():
    profile = current_profile()
    try:
        return jsonify(standings.get_standings(profile["league_id"]))
    except Exception as e:
        return jsonify({"error": f"Could not load standings: {e}"}), 500


@app.route("/api/draft-recap")
def api_draft_recap():
    profile = current_profile()
    try:
        rankings = rankings_engine.get_rankings(profile["league_id"], profile["season"])
        return jsonify(draft_recap.get_draft_recap(profile["league_id"], rankings["players"]))
    except Exception as e:
        return jsonify({"available": False, "message": f"Could not load draft recap: {e}"}), 500


@app.route("/api/defense-strength")
def api_defense_strength():
    profile = current_profile()
    try:
        rankings = rankings_engine.get_rankings(profile["league_id"], profile["season"])
        return jsonify({"defenses": defense_strength.get_defense_rankings(rankings["players"])})
    except Exception as e:
        return jsonify({"error": f"Could not load defense rankings: {e}"}), 500


@app.route("/api/transactions")
def api_transactions():
    profile = current_profile()
    try:
        current_week = bye_weeks.get_current_nfl_week()
        all_players = rankings_engine.get_all_players()
        items = transactions_feed.get_recent_transactions(profile["league_id"], current_week, all_players)
        return jsonify({"transactions": items})
    except Exception as e:
        return jsonify({"error": f"Could not load transactions: {e}"}), 500


@app.route("/api/benchmark")
def api_benchmark():
    profile = current_profile()
    try:
        my_roster_id, _ = lineup_optimizer.get_my_roster_info(profile["league_id"], profile["username"])
        rankings = rankings_engine.get_rankings(profile["league_id"], profile["season"])
        return jsonify(benchmark.build_benchmark(profile["league_id"], my_roster_id, rankings["players"]))
    except Exception as e:
        return jsonify({"available": False, "message": f"Could not build comparison: {e}"}), 500


@app.route("/api/bye-alert")
def api_bye_alert():
    profile = current_profile()
    try:
        current_week = bye_weeks.get_current_nfl_week()
        if not current_week:
            return jsonify({"current_week": None, "on_bye": []})

        roster_ids = lineup_optimizer.get_my_roster(profile["league_id"], profile["username"])
        rankings = rankings_engine.get_rankings(profile["league_id"], profile["season"])
        pool_by_id = {p["player_id"]: p for p in rankings["players"]}

        on_bye = []
        for pid in roster_ids:
            info = pool_by_id.get(pid)
            if info and info.get("bye_week") == current_week:
                on_bye.append({"name": info["name"], "position": info["position"], "team": info["team"]})

        return jsonify({"current_week": current_week, "on_bye": on_bye})
    except Exception as e:
        return jsonify({"error": f"Could not check bye weeks: {e}"}), 500


@app.route("/api/bye-clusters")
def api_bye_clusters():
    profile = current_profile()
    try:
        roster_ids = lineup_optimizer.get_my_roster(profile["league_id"], profile["username"])
        rankings = rankings_engine.get_rankings(profile["league_id"], profile["season"])
        pool_by_id = {p["player_id"]: p for p in rankings["players"]}
        roster_players = [pool_by_id[pid] for pid in roster_ids if pid in pool_by_id]
        clusters = bye_weeks.get_bye_clusters(roster_players)
        return jsonify({"clusters": clusters})
    except Exception as e:
        return jsonify({"error": f"Could not check bye clusters: {e}"}), 500


@app.route("/api/trending")
def api_trending():
    try:
        all_players = rankings_engine.get_all_players()
        return jsonify({"trending": trending.get_trending_adds(all_players)})
    except Exception as e:
        return jsonify({"error": f"Could not load trending players: {e}"}), 500


@app.route("/api/roster-news")
def api_roster_news():
    profile = current_profile()
    try:
        roster_ids = lineup_optimizer.get_my_roster(profile["league_id"], profile["username"])
        rankings = rankings_engine.get_rankings(profile["league_id"], profile["season"])
        pool_by_id = {p["player_id"]: p for p in rankings["players"]}
        roster_names = [pool_by_id[pid]["name"] for pid in roster_ids if pid in pool_by_id]
        watchlist_names = load_watchlist(profile["league_id"])
        names = list(dict.fromkeys(roster_names + watchlist_names))

        if not names:
            return jsonify({"articles": [], "message": "No roster or watchlisted players yet - star a player or draft your team to see news here."})

        result = news_feed.find_news_for_roster(names)
        return jsonify(
            {
                "articles": result["matches"],
                "debug_total_articles_fetched": result["total_articles_fetched"],
                "debug_roster_names_checked": result["roster_names_checked"],
                "debug_feed_errors": result["feed_errors"],
            }
        )
    except Exception as e:
        return jsonify({"error": f"Could not load roster news: {e}"}), 500


@app.route("/api/team-needs")
def api_team_needs():
    profile = current_profile()
    try:
        _, roster_positions, league = rankings_engine.get_league_settings(profile["league_id"])
        drafted_positions = team_needs.get_my_drafted_positions(profile["league_id"], profile["username"])
        result = team_needs.build_needs_report(roster_positions, drafted_positions)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Could not load team needs: {e}"}), 500


@app.route("/api/all-players")
def api_all_players():
    profile = current_profile()
    try:
        rankings = get_enriched_rankings(profile)
        return jsonify({"players": rankings["players"]})
    except Exception as e:
        return jsonify({"error": f"Could not load players: {e}"}), 500


@app.route("/api/lineup")
def api_lineup():
    profile = current_profile()
    try:
        _, roster_positions, league = rankings_engine.get_league_settings(profile["league_id"])
        roster_ids = lineup_optimizer.get_my_roster(profile["league_id"], profile["username"])
        rankings = get_enriched_rankings(profile)
        current_week = bye_weeks.get_current_nfl_week()
        result = lineup_optimizer.optimize_lineup(roster_ids, roster_positions, rankings["players"], current_week)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Could not build your lineup: {e}"}), 500


@app.route("/api/matchup")
def api_matchup():
    profile = current_profile()
    try:
        _, roster_positions, league = rankings_engine.get_league_settings(profile["league_id"])
        rankings = get_enriched_rankings(profile)
        result = matchup_preview.build_matchup_preview(
            profile["league_id"], profile["username"], roster_positions, rankings["players"]
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"available": False, "message": f"Could not load your matchup: {e}"}), 500


@app.route("/api/waivers")
def api_waivers():
    profile = current_profile()
    try:
        _, roster_positions, league = rankings_engine.get_league_settings(profile["league_id"])
        rankings = get_enriched_rankings(profile)
        result = waiver_assistant.build_waiver_report(
            profile["league_id"], profile["username"], roster_positions, rankings["players"]
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Could not build waiver report: {e}"}), 500


@app.route("/api/mock-draft/meta")
def api_mock_draft_meta():
    profile = current_profile()
    try:
        result = mock_draft.get_draft_meta(profile["league_id"], username=profile.get("username"))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Could not load draft info: {e}"}), 500


@app.route("/api/mock-draft", methods=["GET", "POST"])
def api_mock_draft():
    profile = current_profile()
    my_slot = None
    strategy = None

    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        slot_val = data.get("slot")
        my_slot = int(slot_val) if slot_val else None
        raw_strategy = data.get("strategy") or {}
        strategy = {}
        for k, v in raw_strategy.items():
            if not v or v == "BEST":
                continue
            try:
                strategy[int(k)] = v
            except (TypeError, ValueError):
                continue
    else:
        slot_param = request.args.get("slot")
        my_slot = int(slot_param) if slot_param and slot_param.isdigit() else None

    try:
        result = mock_draft.simulate_mock_draft(
            profile["league_id"],
            profile["season"],
            my_slot=my_slot,
            username=profile.get("username"),
            strategy=strategy,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"Could not run mock draft: {e}"}), 500


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    profile = current_profile()
    try:
        rankings_engine.get_rankings(profile["league_id"], profile["season"], force_refresh=True)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    app.run(debug=True, port=port, host="0.0.0.0")
