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
import re
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import crossword
import fallback
import llm
import safety
import sources
import sudoku

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

# Which sections had to relax the freshness rule today, and how far.
FRESHNESS: dict[str, str] = {}

# Anything worth saying about how today was assembled that isn't a failure.
NOTES: list[str] = []

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


def valid_wordle_pair(w: Any) -> bool:
    """Wordle now has an easy and a hard word, like the other puzzles."""
    if not isinstance(w, dict):
        return False
    return all(valid_wordle(w.get(level)) for level in ("easy", "hard"))


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

def _dedupe_creative(day: date, out: dict, seen: dict[str, set[str]]) -> list[str]:
    """Replace anything we've already used with an unused bank entry."""
    swapped: list[str] = []

    for level, salt in (("easy", 3), ("hard", 8)):
        word = out["wordle"][level]["word"].strip().upper()
        if word in seen["wordle"]:
            bank = fallback.WORDLE_WORDS if level == "easy" else fallback.HARD_WORDLE_WORDS
            pick = _pick_unused(bank, lambda t: t[0], seen["wordle"], day, salt)
            if pick:
                out["wordle"][level] = {"word": pick[0], "hint": pick[1],
                                        "fact": out["wordle"][level].get("fact", "")}
                swapped.append(f"wordle.{level}")
                seen["wordle"].add(pick[0])

    if str(out["word_of_day"].get("word", "")).strip().lower() in seen["words"]:
        pick = _pick_unused(fallback.WORDS_OF_DAY, lambda w: w["word"].lower(),
                            seen["words"], day, 0)
        if pick:
            out["word_of_day"] = pick
            swapped.append("word_of_day")

    if _wordkey(out["joke"].get("setup", "")) in seen["jokes"]:
        pick = _pick_unused(fallback.JOKES, lambda j: _wordkey(j["setup"]),
                            seen["jokes"], day, 5)
        if pick:
            out["joke"] = pick
            swapped.append("joke")
            seen["jokes"].add(_wordkey(pick["setup"]))

    # Puzzles are swapped as a pair - the bank stores easy and hard together,
    # and a half-swapped pair would be a worse experience than either.
    for kind, bank, salt in (("math_puzzle", fallback.MATH_PUZZLES, 1),
                             ("logic_puzzle", fallback.LOGIC_PUZZLES, 2)):
        node = out.get(kind) or {}
        keys = {_wordkey((node.get(lv) or {}).get("question", ""))
                for lv in ("easy", "hard")}
        if not (keys & seen["puzzles"]):
            continue
        pick = _pick_unused_pair(bank, seen["puzzles"], day, salt)
        if pick:
            out[kind] = pick
            swapped.append(kind)
            for lv in ("easy", "hard"):
                seen["puzzles"].add(_wordkey(pick[lv]["question"]))

    return swapped


def _pick_unused_pair(bank: list, used: set, day: date, salt: int):
    """Like _pick_unused, but a puzzle pair only counts as free if BOTH
    levels are unused - otherwise the 9-year-old gets a fresh puzzle and the
    11-year-old gets yesterday's again."""
    if not bank:
        return None
    start = (day.toordinal() + salt) % len(bank)
    for k in range(len(bank)):
        item = bank[(start + k) % len(bank)]
        keys = {_wordkey(item[lv]["question"]) for lv in ("easy", "hard")}
        if not (keys & used):
            return item
    return bank[start]   # bank exhausted; any choice repeats something


def _events_from_wikipedia(raw_events: list[dict], limit: int = 3) -> list[dict]:
    """Build the history section straight from Wikipedia's own wording.

    The bank's on_this_day is an apology - "we could not reach our history
    source". Showing that when Wikipedia answered perfectly well and it was
    only the model's formatting that went missing is a lie to a nine-year-old.
    Plain real events beat a polished apology.
    """
    out = []
    for e in raw_events:
        text = str(e.get("text") or "").strip()
        year = e.get("year")
        if not text or not year or not safety.is_safe(text):
            continue
        head = re.split(r"[:;.]", text)[0].strip()
        if len(head) > 72:
            head = head[:69].rsplit(" ", 1)[0] + "..."
        out.append({"year": year, "headline": head, "blurb": text, "why_cool": ""})
        if len(out) == limit:
            break
    return out


def _merge_creative(day: date, generated: dict | None,
                    raw_events: list[dict] | None = None) -> tuple[dict, list[str]]:
    bank = fallback.creative_bank(day)
    used_bank: list[str] = []
    out: dict[str, Any] = {}
    checks = {
        "word_of_day": valid_word_of_day,
        "math_puzzle": valid_puzzle_pair,
        "logic_puzzle": valid_puzzle_pair,
        "connections": valid_connections,
        "wordle": valid_wordle_pair,
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
    for level in ("easy", "hard"):
        out["wordle"][level]["word"] = out["wordle"][level]["word"].strip().upper()

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
    # The section is a three-card row. When the safety filter thins Claude's
    # three down to two, a gap is left in the grid - so top it back up from the
    # same Wikipedia list Claude was working from, skipping years it already
    # used. Better a plainer third card than a hole.
    if 0 < len(out["on_this_day"]) < 3:
        had = len(out["on_this_day"])
        used_years = {str(e.get("year")) for e in out["on_this_day"]}
        for extra in _events_from_wikipedia(raw_events or [], limit=8):
            if str(extra["year"]) in used_years:
                continue
            out["on_this_day"].append(extra)
            used_years.add(str(extra["year"]))
            if len(out["on_this_day"]) == 3:
                break
        added = len(out["on_this_day"]) - had
        if added:
            NOTES.append(f"on_this_day: Claude returned {had} usable event" + ("s" if had != 1 else "") + ", "
                         f"topped up with {added} from Wikipedia")

    if not out["on_this_day"]:
        from_wiki = _events_from_wikipedia(raw_events or [])
        if from_wiki:
            out["on_this_day"] = from_wiki
            NOTES.append("on_this_day: used Wikipedia's own wording "
                         "(the model didn't return this section)")
        else:
            out["on_this_day"] = bank["on_this_day"]
            used_bank.append("on_this_day")
    return out, used_bank


def _merge_news(
    day: date,
    generated: dict | None,
    seen_heads: set[str] | None = None,
    seen_links: set[str] | None = None,
) -> tuple[dict, list[str]]:
    bank = fallback.news_bank(day)
    used_bank: list[str] = []
    out: dict[str, Any] = {}

    # Sections allowed to be empty without it meaning anything is wrong.
    # westwindsor is empty most days BY DESIGN - the local topical gate is
    # strict on purpose. Reporting that as "degraded" every single day would
    # train you to ignore the health signal, which defeats its whole point.
    OPTIONAL = {"westwindsor"}
    empty: list[str] = []
    seen_heads = seen_heads or set()
    seen_links = seen_links or set()

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
            # The model can restate a story we already ran. Prefer the fresh
            # ones, but never let this empty the section.
            if clean:
                clean, tier = prefer_fresh(
                    clean, seen_heads, seen_links, title_key="headline"
                )
                if tier != "fresh":
                    FRESHNESS[key] = tier
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
        and not _is_repeat(fg.get("title", ""), fg.get("link", ""), seen_heads, seen_links)
        # A three-line summary of nothing in particular is not a story. This is
        # what "stale and incomplete" looked like in practice.
        and len(str(fg.get("story", ""))) >= 400
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
    FRESHNESS.clear()
    NOTES.clear()

    all_events = sources.fetch_on_this_day(day)
    raw_events = safety.scrub_events(all_events)
    DROPPED["wikimedia_events"] = len(all_events) - len(raw_events)

    seen_heads, seen_links, recent_titles = recent_signatures(day)
    seen_creative = recent_creative(day)
    DROPPED["repeats_from_previous_days"] = 0

    raw_feeds = sources.fetch_all_feeds()
    feeds = {}
    for key, items in raw_feeds.items():
        before = len(items)
        items, tier = prefer_fresh(items, seen_heads, seen_links)
        DROPPED["repeats_from_previous_days"] += before - len(items)
        if tier != "fresh" and before:
            FRESHNESS[key] = tier
        kept = safety.filter_items(
            items,
            sports=key in ("eagles", "nfl", "tennis", "cricket"),
            local=key == "westwindsor",
            limit=6,
        )
        DROPPED["feed_" + key] = len(items) - len(kept)
        feeds[key] = kept

    if llm.have_key():
        creative_raw = llm.generate_creative(day, raw_events, avoid=seen_creative)
        news_raw = llm.edit_news(day, feeds, recent_titles=sorted(recent_titles))
    else:
        creative_raw = news_raw = None
        llm.LLM_LOG["creative"] = llm.LLM_LOG["news"] = "no ANTHROPIC_API_KEY - using bank"

    creative, bank_creative = _merge_creative(day, creative_raw, raw_events)
    # Belt and braces: even with the prompt told what to avoid, swap out
    # anything that still came back as a repeat.
    swapped = _dedupe_creative(day, creative, seen_creative)
    news, bank_news = _merge_news(day, news_raw, seen_heads, seen_links)
    empty_sections = news.pop("_empty_sections", [])

    # Sudoku is generated algorithmically, not by the model: a puzzle is only a
    # puzzle if the solution is unique, and that must be proved, not hoped for.
    try:
        puzzles = sudoku.daily(day)
        if not (sudoku.is_valid(puzzles["easy"]) and sudoku.is_valid(puzzles["hard"])):
            log.error("generated sudoku failed validation - omitting the section")
            puzzles = None
    except Exception:  # noqa: BLE001
        log.exception("sudoku generation failed")
        puzzles = None

    # Same reasoning as the Sudoku: a crossword whose crossings disagree cannot
    # be finished, and a child experiences that as her own failure rather than
    # ours. So it is built and proved here, never asked for.
    try:
        xword = crossword.daily(day)
        if not (crossword.is_valid(xword.get("easy"))
                and crossword.is_valid(xword.get("hard"))):
            log.error("generated crossword failed validation - omitting it")
            xword = None
    except Exception:  # noqa: BLE001
        log.exception("crossword generation failed")
        xword = None

    payload = {
        "date": day.isoformat(),
        "sudoku": puzzles,
        "crossword": xword,
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
            "freshness_relaxed": dict(FRESHNESS),
            "creative_swapped_to_avoid_repeat": swapped,
            "notes": list(NOTES),
            "links_mode": LINKS_MODE,
        },
    }
    return payload


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# don't repeat yourself
# --------------------------------------------------------------------------
# Feeds move slowly. Without this the same Eagles training-camp story and the
# same feel-good piece appear three mornings running, which is the fastest way
# to make a daily page feel dead.

DEDUP_DAYS = 7
_NEWS_KEYS = ("kids_news", "eagles", "nfl", "tennis", "cricket", "westwindsor")


def _sig(text: str) -> str:
    """Loose signature for a headline, so light rewording still matches."""
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())[:60]


# Words that carry no identity. Dropping them is what lets "Why did the math
# book look sad?" and "Why did the math book look SO sad?" collapse together -
# _sig treated those as two different jokes, which is exactly how the same
# gag got through the repeat check on consecutive days.
_FILLER = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "as", "by",
    "is", "are", "was", "were", "be", "been", "did", "do", "does", "so",
    "very", "just", "that", "this", "it", "its", "you", "your", "if", "then",
    "what", "which", "who", "how", "many", "much", "has", "have", "had",
    "with", "for", "from", "but", "not", "there", "here", "get", "gets",
}


def _wordkey(text: str) -> str:
    """Identity of a joke or a puzzle, robust to rewording.

    Keeps the distinctive words and any numbers, drops filler, ignores order.
    Numbers matter: two garden-area problems with different dimensions are
    genuinely different puzzles and must not collide.
    """
    words = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return " ".join(sorted({w for w in words if w not in _FILLER}))[:220]


def recent_signatures(
    day: date, back: int = DEDUP_DAYS
) -> tuple[set[str], set[str], set[str]]:
    """Headline signatures, links and readable titles from the previous days."""
    heads: set[str] = set()
    links: set[str] = set()
    titles: set[str] = set()
    for i in range(1, back + 1):
        prev = day - timedelta(days=i)
        payload = _read_cache(prev)
        if payload is None:
            payload = _pull_from_hub(prev)
        if not payload:
            continue
        for key in _NEWS_KEYS:
            for item in payload.get(key) or []:
                if isinstance(item, dict):
                    if item.get("headline"):
                        heads.add(_sig(item["headline"]))
                        titles.add(item["headline"])
                    if item.get("link"):
                        links.add(item["link"].split("?")[0])
        fg = payload.get("feelgood")
        if isinstance(fg, dict) and fg.get("title"):
            heads.add(_sig(fg["title"]))
            titles.add(fg["title"])
            if fg.get("link"):
                links.add(fg["link"].split("?")[0])
    return heads, links, titles


def _is_same_article(link: str, links: set[str]) -> bool:
    """The identical URL. Always a repeat, no exceptions."""
    return bool(link) and link.split("?")[0] in links


def _is_repeat(text: str, link: str, heads: set[str], links: set[str]) -> bool:
    if _is_same_article(link, links):
        return True
    return _sig(text) in heads


def prefer_fresh(items: list[dict], heads: set[str], links: set[str],
                 title_key: str = "title", link_key: str = "link") -> tuple[list[dict], str]:
    """Prefer unseen items, but never return an empty list.

    De-duplication started as a hard filter and blanked all four sports
    sections on day two: those feeds barely move, so once yesterday used the
    top stories, everything left looked like a repeat. Freshness is a
    preference now, applied in tiers:

        1. items never seen before          - ideal
        2. failing that, items whose URL is new (headline may be similar)
        3. failing that, everything         - a stale card beats a blank one
    """
    def link_of(i): return i.get(link_key, "") or ""
    def title_of(i): return i.get(title_key, "") or ""

    fresh = [i for i in items
             if not _is_repeat(title_of(i), link_of(i), heads, links)]
    if fresh:
        return fresh, "fresh"

    new_url = [i for i in items if not _is_same_article(link_of(i), links)]
    if new_url:
        return new_url, "same-topic, new article"

    return items, "nothing new today - reusing"


# The news sections have had de-duplication for a while. The creative content -
# Wordle word, joke, word of the day - had none at all: the model is asked for
# "a word a 9-year-old knows" with no memory of yesterday, out of a small
# effective vocabulary. Over a 30-day summer that repeats sooner or later.

CREATIVE_MEMORY_DAYS = 21


def recent_creative(day: date, back: int = CREATIVE_MEMORY_DAYS) -> dict[str, set[str]]:
    """Everything creative we've already served: words, jokes, puzzles, groups."""
    out = {"wordle": set(), "words": set(), "jokes": set(),
           "categories": set(), "puzzles": set()}
    for i in range(1, back + 1):
        prev = day - timedelta(days=i)
        payload = _read_cache(prev) or _pull_from_hub(prev)
        if not payload:
            continue
        # Math and logic puzzles had no repeat protection at all, which is how
        # the same riddle ran three days straight.
        for kind in ("math_puzzle", "logic_puzzle"):
            node = payload.get(kind) or {}
            for level in ("easy", "hard"):
                lv = node.get(level)
                if isinstance(lv, dict) and lv.get("question"):
                    out["puzzles"].add(_wordkey(lv["question"]))
        w = payload.get("wordle") or {}
        for level in ("easy", "hard"):
            node = w.get(level)
            if isinstance(node, dict) and node.get("word"):
                out["wordle"].add(str(node["word"]).strip().upper())
        wod = payload.get("word_of_day") or {}
        if wod.get("word"):
            out["words"].add(str(wod["word"]).strip().lower())
        joke = payload.get("joke") or {}
        if joke.get("setup"):
            out["jokes"].add(_wordkey(joke["setup"]))
        for g in (payload.get("connections") or {}).get("groups", []):
            if isinstance(g, dict) and g.get("name"):
                out["categories"].add(_sig(g["name"]))
    return out


def _pick_unused(bank: list, key_of, used: set, day: date, salt: int):
    """Deterministically walk the bank for an entry not used recently."""
    if not bank:
        return None
    start = (day.toordinal() + salt) % len(bank)
    for k in range(len(bank)):
        item = bank[(start + k) % len(bank)]
        if key_of(item) not in used:
            return item
    return bank[start]   # bank exhausted; unavoidable repeat


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
