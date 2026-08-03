"""Live data sources: RSS feeds and the Wikimedia On-This-Day API.

Every function here is defensive: it returns [] on any failure rather than
raising, and the caller decides whether to fall back to an LLM-generated
version. Each source records its outcome in SOURCE_LOG for /health.
"""

from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

import httpx

log = logging.getLogger("kidsdaily.sources")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 KidsDailySite/1.0"
)
TIMEOUT = 15.0

# Populated on each build so /health can show which sources worked.
SOURCE_LOG: dict[str, str] = {}


def _note(key: str, msg: str) -> None:
    SOURCE_LOG[key] = msg
    log.info("source %s: %s", key, msg)


def _clean(text: str) -> str:
    """Strip HTML tags and entities out of an RSS description."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _get(url: str) -> str | None:
    try:
        with httpx.Client(
            timeout=TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": UA, "Accept": "*/*"},
        ) as client:
            r = client.get(url)
            r.raise_for_status()
            return r.text
    except Exception as exc:  # noqa: BLE001 - never let a source break the build
        log.warning("fetch failed %s: %s", url, exc)
        return None


def parse_rss(xml_text: str, limit: int = 8) -> list[dict[str, str]]:
    """Parse RSS 2.0 or Atom into a list of {title, link, summary, source}."""
    items: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    # RSS 2.0
    for node in root.iter("item"):
        title = _clean(node.findtext("title") or "")
        link = (node.findtext("link") or "").strip()
        summary = _clean(node.findtext("description") or "")
        source = _clean(node.findtext("source") or "")
        if title:
            items.append(
                {"title": title, "link": link, "summary": summary, "source": source}
            )
        if len(items) >= limit:
            return items

    # Atom
    ns = "{http://www.w3.org/2005/Atom}"
    for node in root.iter(f"{ns}entry"):
        title = _clean(node.findtext(f"{ns}title") or "")
        link_el = node.find(f"{ns}link")
        link = (link_el.get("href") if link_el is not None else "") or ""
        summary = _clean(
            node.findtext(f"{ns}summary") or node.findtext(f"{ns}content") or ""
        )
        if title:
            items.append(
                {"title": title, "link": link, "summary": summary, "source": ""}
            )
        if len(items) >= limit:
            break
    return items


def fetch_feed(key: str, urls: list[str], limit: int = 8) -> list[dict[str, str]]:
    """Try each candidate URL in order; return items from the first that works."""
    for url in urls:
        text = _get(url)
        if not text:
            continue
        items = parse_rss(text, limit=limit)
        if items:
            _note(key, f"rss ok ({len(items)} items) from {url.split('?')[0]}")
            return items
    _note(key, "rss failed - falling back to Claude web search")
    return []


def google_news(query: str, hl: str = "en-US", gl: str = "US", ceid: str = "US:en") -> str:
    q = query.replace(" ", "+")
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


# Order matters. Direct publisher feeds come first because their links point
# straight at the publisher and survive the allowlist in safety.py. Google News
# is the fallback: broad coverage, but its links are redirects through
# news.google.com to a site we haven't vetted, so they get stripped and the
# story appears without a "Read the full story" button.
FEEDS: dict[str, list[str]] = {
    "kids_news": [
        "https://feeds.bbci.co.uk/newsround/rss.xml",
        "http://feeds.bbci.co.uk/newsround/rss.xml",
        google_news("news for kids"),
    ],
    "eagles": [
        # Bleeding Green Nation - SB Nation's Eagles site. Two candidate paths
        # because the feed URL is unverified from the build environment.
        "https://www.bleedinggreennation.com/rss/index.xml",
        "https://www.bleedinggreennation.com/rss/current.xml",
        "https://www.espn.com/espn/rss/nfl/news",
        google_news("Philadelphia Eagles"),
    ],
    "tennis": [
        # BBC Sport first: links land on bbc.co.uk, which is allowlisted, and
        # the feed is reliably reachable. ESPN's tennis feed went stale and did
        # not respond from Render on the first live run, so it sits behind.
        "https://feeds.bbci.co.uk/sport/tennis/rss.xml",
        "https://www.espn.com/espn/rss/tennis/news",
        google_news("tennis ATP WTA"),
    ],
    "cricket": [
        "https://www.espncricinfo.com/rss/content/story/feeds/6.xml",
        google_news("India cricket team", hl="en-IN", gl="IN", ceid="IN:en"),
    ],
    "nfl": [
        # ESPN first for US-centric, current coverage. BBC second because its
        # links are allowlisted and BBC feeds are reliably reachable from
        # Render. Google News last (its links get stripped).
        "https://www.espn.com/espn/rss/nfl/news",
        "https://feeds.bbci.co.uk/sport/american-football/rss.xml",
        google_news("NFL football"),
    ],
    "westwindsor": [
        # Local news for West Windsor Township, Mercer County NJ. None of these
        # could be verified from the build environment, so the chain is long
        # and /health will report which one actually answered.
        "https://planetprinceton.com/feed/",
        "https://patch.com/new-jersey/westwindsor/rss",
        "https://www.tapinto.net/towns/west-windsor/rss",
        google_news('"West Windsor" OR "Plainsboro" New Jersey'),
    ],
    "feelgood": [
        # Dedicated good-news outlets first. The old Google News query returned
        # thin aggregator blurbs with no names or places, which is exactly how
        # we ended up with a vague "someone gave someone an ice cream" story.
        "https://www.goodnewsnetwork.org/feed/",
        "https://www.positive.news/feed/",
        "https://reasonstobecheerful.world/feed/",
        google_news("heartwarming kindness good news"),
    ],
}


def fetch_all_feeds() -> dict[str, list[dict[str, str]]]:
    return {key: fetch_feed(key, urls) for key, urls in FEEDS.items()}


def fetch_on_this_day(day: date) -> list[dict[str, Any]]:
    """Wikimedia's curated 'selected' events for this month/day."""
    url = (
        "https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/selected/"
        f"{day.month:02d}/{day.day:02d}"
    )
    text = _get(url)
    if not text:
        _note("on_this_day", "wikimedia failed - Claude will supply events")
        return []
    try:
        import json

        data = json.loads(text)
    except Exception:  # noqa: BLE001
        _note("on_this_day", "wikimedia returned unparseable JSON")
        return []

    events = []
    for ev in (data.get("selected") or [])[:12]:
        events.append({"year": ev.get("year"), "text": _clean(ev.get("text") or "")})
    _note("on_this_day", f"wikimedia ok ({len(events)} events)")
    return events
