"""
Weekly NFL schedule (who plays whom) and game-day weather, from ESPN's
public scoreboard endpoint - no key required.
"""

import urllib.request
import json

# ESPN's team abbreviations differ from Sleeper's in a couple of spots
ESPN_TO_SLEEPER_ABBR = {
    "WSH": "WAS",
    "JAC": "JAX",
}


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


def _normalize(abbr):
    if not abbr:
        return abbr
    return ESPN_TO_SLEEPER_ABBR.get(abbr, abbr)


def get_week_schedule(season, week):
    """Returns {"opponents": {team: opponent_team}, "weather": {team: {...}}}
    for the given week. Weather is only present for some games (outdoor
    stadiums, and only once ESPN has a forecast) - absence isn't an error."""
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        f"?seasontype=2&week={week}&year={season}"
    )
    try:
        data = _fetch_json(url)
    except Exception:
        return {"opponents": {}, "weather": {}}

    opponents = {}
    weather = {}

    for event in data.get("events", []):
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competitors = competitions[0].get("competitors") or []
        if len(competitors) != 2:
            continue

        teams = []
        for c in competitors:
            abbr = _normalize((c.get("team") or {}).get("abbreviation"))
            if abbr:
                teams.append(abbr)

        if len(teams) == 2:
            opponents[teams[0]] = teams[1]
            opponents[teams[1]] = teams[0]

        weather_info = competitions[0].get("weather")
        if weather_info:
            summary = {
                "condition": weather_info.get("displayValue"),
                "temperature": weather_info.get("temperature"),
            }
            for abbr in teams:
                weather[abbr] = summary

    return {"opponents": opponents, "weather": weather}
