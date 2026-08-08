"""
Defense strength rankings.
Honest note: this ranks each team's DEF unit by how well it scores in
your league's format (sacks, turnovers, points allowed thresholds) as a
general proxy for "how tough is this defense overall" - it isn't a
position-specific matchup rating (e.g. "tough against RBs" specifically),
since that data isn't reliably available from a free source. Pair this
with your own knowledge of who a player's next opponent is.
"""


def attach_matchup_info(players, schedule_data, defense_rankings):
    """Attaches each offensive player's real opponent this week, plus
    that opponent's defense strength/label, and weather if available."""
    opponents = schedule_data.get("opponents", {})
    weather = schedule_data.get("weather", {})
    defense_by_team = {d["team"]: d for d in defense_rankings}

    for p in players:
        if p.get("position") not in ("QB", "RB", "WR", "TE", "K"):
            continue
        team = p.get("team")
        opponent = opponents.get(team)
        p["opponent"] = opponent
        if opponent and opponent in defense_by_team:
            opp_def = defense_by_team[opponent]
            p["matchup_label"] = opp_def["strength_label"]
            p["opponent_def_rank"] = opp_def["strength_rank"]
        else:
            p["matchup_label"] = None
            p["opponent_def_rank"] = None
        p["weather"] = weather.get(team)

    return players


def get_defense_rankings(player_pool):
    defenses = [p for p in player_pool if p.get("position") == "DEF" and p.get("per_game_avg") is not None]
    defenses.sort(key=lambda p: p["per_game_avg"], reverse=True)
    for i, d in enumerate(defenses, start=1):
        d_rank = i
        d["strength_rank"] = d_rank
        if d_rank <= 10:
            d["strength_label"] = "Tough matchup"
        elif d_rank <= 22:
            d["strength_label"] = "Average"
        else:
            d["strength_label"] = "Favorable matchup"
    return defenses
