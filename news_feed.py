"""
Roster news feed.
Pulls headlines from legitimate, publicly syndicated NFL news RSS feeds
and filters them down to just the players on your roster - no scraping,
no fabricated content, just real headlines and links to the source.
"""

import urllib.request
import xml.etree.ElementTree as ET

NEWS_FEEDS = [
    ("ESPN NFL", "https://www.espn.com/espn/rss/nfl/news"),
]


def _fetch_text(url, timeout=15):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return resp.read()


def _parse_rss(xml_bytes, source_name):
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if title and link:
            items.append(
                {
                    "title": title,
                    "link": link,
                    "description": description,
                    "pub_date": pub_date,
                    "source": source_name,
                }
            )
    return items


def find_news_for_roster(player_names, max_articles=15):
    """player_names: list of full player names on your roster.
    Returns news articles that mention any of them, most recent first
    (feed order is already newest-first)."""
    all_articles = []
    feed_errors = []
    for source_name, url in NEWS_FEEDS:
        try:
            xml_bytes = _fetch_text(url)
            parsed = _parse_rss(xml_bytes, source_name)
            all_articles.extend(parsed)
        except Exception as e:
            feed_errors.append(f"{source_name}: {e}")

    matches = []
    seen_links = set()
    for article in all_articles:
        haystack = (article["title"] + " " + article["description"]).lower()
        matched_players = [name for name in player_names if name.lower() in haystack]
        if matched_players and article["link"] not in seen_links:
            article["matched_players"] = matched_players
            matches.append(article)
            seen_links.add(article["link"])

    return {
        "matches": matches[:max_articles],
        "total_articles_fetched": len(all_articles),
        "roster_names_checked": player_names,
        "feed_errors": feed_errors,
    }
