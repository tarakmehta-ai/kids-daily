"""Assembles the day's payload and caches it.

Flow for a given date:
    cache hit?  -> return it
    otherwise   -> fetch feeds + Wikimedia
                -> safety-filter the raw headlines
                -> ask Claude for creative content and kid-friendly news
                -> validate; swap in the offline bank for anything that failed
                -> cache and return

Validation matters more than it looks. A malformed Connections grid (repeated
words, wrong group sizes) produces a game that literally cannot be finished, so
we check structure before it ever reaches a child.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import fallback
import llm
import safety
import sources

log = logging.getLogger("kidsdaily.builder")

TZ = ZoneInfo(os.environ.get("SITE_TZ", "America/New_York"))
CACHE_DIR = Path(os.environ.get("CACHE_DIR", "/tmp/kidsdaily"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# off | allowlist | all   (see safety.safe_url)
#
# Defaults to "allowlist": a "Read the full story" link appears only when the
# URL points at a domain in safety.ALLOWED_LINK_DOMAINS. Set LINKS_MODE=off in
# the Space settings to remove outbound links entirely.
LINKS_MODE = os.environ.get("LINKS_MODE", "allowlist").strip().lower()

# How much each filter threw away today. Surfaced by /health so the filtering
# is observable rather than a black box.
DROPPED: dict[str, int] = {}

# One build at a time. Without this, two kids loading the page at 7am would
# each kick off a full generation (and each cost an API call).
_LOCK = threading.Lock()


# Hour (0-23, local time) at which the site starts serving the NEXT day's page.
# 0 = normal midnight rollover. 20 = the new page appears at 8pm, so the kids
# get fresh content in the evening and it stays put until 8pm the next night.
#
# This shifts the content day only. Analytics stay on calendar days, so the
# evening summary still reports "what happened today" in the ordinary sense.
def _rollover_hour() -> int:
    try:
        h = int(os.environ.get("DAY_ROLLOVER_HOUR", "0") or 0)
    except ValueError:
        return 0
    return h if 0 <= h <= 23 else 0


def today() -> date:
    """The date whose page should currently be showing."""
    now = datetime.now(TZ)
    hour = _rollover_hour()
    if hour and now.hour >= hour:
        return (now + timedelta(days=1)).date()
    return now.date()


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def valid_connections(c: Any) -> bool:
    if not isinstance(c, dict):
        return False
    groups = c.get("groups")
    if not isinstance(groups, list) or len(groups) != 4:
        return False
    seen: set[str] = set()
    for g in groups:
        words = g.get("words") if isinstance(g, dict) else None
        if not isinstance(words, list) or len(words) != 4:
            return False
        if not g.get("name") or not safety.is_safe(str(g.get("name"))):
            return False
        for w in words:
            if not isinstance(w, str) or not w.strip():
                return False
            if not safety.word_is_clean(w):  # no rude tiles on the board
                return False
            key = w.strip().upper()
            if key in seen:  # a repeated tile makes the grid unsolvable
                return False
            seen.add(key)
    return len(seen) == 16


def valid_wordle(w: Any) -> bool:
    if not isinstance(w, dict):
        return False
    word = str(w.get("word", "")).strip().upper()
    if not (len(word) == 5 and word.isalpha() and word.isascii()):
        return False
    if not safety.word_is_clean(word):
        return False
    return safety.is_safe(str(w.get("hint", "")))


def valid_puzzle_pair(p: Any) -> bool:
    if not isinstance(p, dict):
        return False
    for level in ("easy", "hard"):
        lv = p.get(level)
        if not isinstance(lv, dict):
            return False
        if not lv.get("question") or not lv.get("answer"):
            return False
        if not safety.is_safe(safety.text_of(lv, "question", "answer", "solution")):
            return False
    return True


def valid_word_of_day(w: Any) -> bool:
    if not (isinstance(w, dict) and w.get("word") and w.get("definition")):
        return False
    return safety.is_safe(
        safety.text_of(w, "word", "definition", "example", "origin", "pronunciation")
    )


def valid_joke(j: Any) -> bool:
    if not (isinstance(j, dict) and j.get("setup") and j.get("punchline")):
        return False
    return safety.is_safe(safety.text_of(j, "setup", "punchline"))


def _normalise_connections(c: dict) -> dict:
    for g in c["groups"]:
        g["words"] = [w.strip().upper() for w in g["words"]]
        g["difficulty"] = int(g.get("difficulty") or 1)
    return c


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def _merge_creative(day: date, generated: dict | None) -> tuple[dict, list[str]]:
    bank = fallback.creative_bank(day)
    used_bank: list[str] = []
    out: dict[str, Any] = {}
    checks = {
        "word_of_day": valid_word_of_day,
        "math_puzzle": valid_puzzle_pair,
        "logic_puzzle": valid_puzzle_pair,
        "connections": valid_connections,
        "wordle": valid_wordle,
        "joke": valid_joke,
    }
    for key, check in checks.items():
        value = (generated or {}).get(key)
        if check(value):
            out[key] = value
        else:
            out[key] = bank[key]
            used_bank.append(key)

    out["connections"] = _normalise_connections(out["connections"])
    out["wordle"]["word"] = out["wordle"]["word"].strip().upper()

    events = (generated or {}).get("on_this_day")
    if isinstance(events, list) and events:
        safe_events = [
            e for e in events
            if isinstance(e, dict)
            and e.get("blurb")
            and safety.is_safe(safety.text_of(e, "headline", "blurb", "why_cool"))
        ]
        out["on_this_day"] = safe_events[:3]
        DROPPED["on_this_day"] = len(events) - len(safe_events)
    else:
        out["on_this_day"] = []
    if not out["on_this_day"]:
        out["on_this_day"] = bank["on_this_day"]
        used_bank.append("on_this_day")
    return out, used_bank


def _merge_news(day: date, generated: dict | None) -> tuple[dict, list[str]]:
    bank = fallback.news_bank(day)
    used_bank: list[str] = []
    out: dict[str, Any] = {}

    # Sections allowed to be empty without it meaning anything is wrong.
    # westwindsor is empty most days BY DESIGN - the local topical gate is
    # strict on purpose. Reporting that as "degraded" every single day would
    # train you to ignore the health signal, which defeats its whole point.
    OPTIONAL = {"westwindsor"}
    empty: list[str] = []

    for key in ("kids_news", "eagles", "nfl", "tennis", "cricket", "westwindsor"):
        items = (generated or {}).get(key)
        if isinstance(items, list):
            is_sport = key in ("eagles", "nfl", "tennis", "cricket")
            clean = []
            for i in items:
                if not (isinstance(i, dict) and i.get("headline")):
                    continue
                blob = safety.text_of(i, "headline", "summary", "talk_about_it", "source")
                # Local goes through the stricter topical gate a second time,
                # because the model can introduce detail the raw headline
                # didn't have.
                if key == "westwindsor":
                    if not safety.is_local_safe(blob):
                        continue
                elif not safety.is_safe(blob, sports=is_sport):
                    continue
                # A link that fails screening is removed, but the story stays -
                # the summary on the page is the point, not the click-through.
                i["link"] = safety.safe_url(i.get("link", ""), mode=LINKS_MODE)
                clean.append(i)
            DROPPED[key] = len(items) - len(clean)
            out[key] = clean
        else:
            out[key] = []
        if not out[key]:
            empty.append(key)
            # Only a non-optional empty section counts as something going wrong.
            if key not in OPTIONAL:
                used_bank.append(key)

    fg = (generated or {}).get("feelgood")
    if (
        isinstance(fg, dict)
        and fg.get("title")
        and fg.get("story")
        and safety.is_safe(safety.text_of(fg, "title", "story", "lesson", "source"))
    ):
        fg.setdefault("kind", "true")
        fg["link"] = safety.safe_url(fg.get("link", ""), mode=LINKS_MODE)
        out["feelgood"] = fg
    else:
        out["feelgood"] = bank["feelgood"]
        used_bank.append("feelgood")
    out["_empty_sections"] = empty
    return out, used_bank


def build(day: date) -> dict:
    """Generate the full payload for a date. Never raises."""
    sources.SOURCE_LOG.clear()
    llm.LLM_LOG.clear()
    DROPPED.clear()

    all_events = sources.fetch_on_this_day(day)
    raw_events = safety.scrub_events(all_events)
    DROPPED["wikimedia_events"] = len(all_events) - len(raw_events)

    raw_feeds = sources.fetch_all_feeds()
    feeds = {}
    for key, items in raw_feeds.items():
        kept = safety.filter_items(
            items,
            sports=key in ("eagles", "nfl", "tennis", "cricket"),
            local=key == "westwindsor",
            limit=6,
        )
        DROPPED["feed_" + key] = len(items) - len(kept)
        feeds[key] = kept

    if llm.have_key():
        creative_raw = llm.generate_creative(day, raw_events)
        news_raw = llm.edit_news(day, feeds)
    else:
        creative_raw = news_raw = None
        llm.LLM_LOG["creative"] = llm.LLM_LOG["news"] = "no ANTHROPIC_API_KEY - using bank"

    creative, bank_creative = _merge_creative(day, creative_raw)
    news, bank_news = _merge_news(day, news_raw)
    empty_sections = news.pop("_empty_sections", [])

    payload = {
        "date": day.isoformat(),
        "date_pretty": day.strftime("%A, %B %d, %Y").replace(" 0", " "),
        "generated_at": datetime.now(TZ).isoformat(),
        **creative,
        **news,
        "diagnostics": {
            "sources": dict(sources.SOURCE_LOG),
            "llm": dict(llm.LLM_LOG),
            "fell_back_to_bank": sorted(set(bank_creative + bank_news)),
            "empty_sections": empty_sections,
            "blocked_by_filter": {k: v for k, v in DROPPED.items() if v},
            "links_mode": LINKS_MODE,
        },
    }
    return payload


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------

def _cache_path(day: date) -> Path:
    return CACHE_DIR / f"{day.isoformat()}.json"


def _read_cache(day: date) -> dict | None:
    path = _cache_path(day)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            log.warning("corrupt cache file %s - rebuilding", path)
    return None


def _write_cache(day: date, payload: dict) -> None:
    try:
        _cache_path(day).write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    except Exception:  # noqa: BLE001
        log.warning("could not write cache")
    _push_to_hub(day)


def _push_to_hub(day: date) -> None:
    """Optional: mirror the cache to a private HF dataset.

    Free Spaces have ephemeral disk, so without this the Space regenerates
    (and pays for) the day again after every sleep/restart. Set
    HF_TOKEN + CACHE_DATASET_REPO to switch it on.
    """
    repo = os.environ.get("CACHE_DATASET_REPO")
    token = os.environ.get("HF_TOKEN")
    if not (repo and token):
        return
    try:
        from huggingface_hub import HfApi

        HfApi(token=token).upload_file(
            path_or_fileobj=str(_cache_path(day)),
            path_in_repo=f"{day.isoformat()}.json",
            repo_id=repo,
            repo_type="dataset",
        )
        log.info("cache mirrored to %s", repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("hub cache push failed: %s", exc)


def _pull_from_hub(day: date) -> dict | None:
    repo = os.environ.get("CACHE_DATASET_REPO")
    token = os.environ.get("HF_TOKEN")
    if not (repo and token):
        return None
    try:
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(
            repo_id=repo,
            filename=f"{day.isoformat()}.json",
            repo_type="dataset",
            token=token,
        )
        data = json.loads(Path(path).read_text())
        _cache_path(day).write_text(json.dumps(data, ensure_ascii=False, indent=1))
        log.info("cache restored from hub")
        return data
    except Exception:  # noqa: BLE001
        return None


def get_day(day: date | None = None, *, force: bool = False) -> dict:
    day = day or today()
    if not force:
        cached = _read_cache(day) or _pull_from_hub(day)
        if cached:
            return cached
    with _LOCK:
        # Re-check: another request may have built it while we waited.
        if not force:
            cached = _read_cache(day)
            if cached:
                return cached
        payload = build(day)
        _write_cache(day, payload)
        return payload
