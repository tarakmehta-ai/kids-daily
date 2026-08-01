"""Engagement tracking.

What it records: how long each section was actually on screen, which puzzles
got opened, which games were finished, which links were clicked. Enough to
answer "what do they actually use" and "what should I drop".

What it deliberately does NOT record: no names, no accounts, no IP addresses,
no text they type, no guesses they make, no cookies. A visit is identified by a
random id generated in the browser that survives only until the tab closes.
The only thing resembling identity is which age button is selected, which is a
rough proxy for which kid is looking.

Storage: one JSONL file per day. Render's free plan has no persistent disk, so
if HF_TOKEN + STATS_DATASET_REPO are set the files are mirrored to a private
HuggingFace dataset and pulled back on boot. Without that, stats reset every
time the service sleeps.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

log = logging.getLogger("kidsdaily.analytics")

TZ = ZoneInfo(os.environ.get("SITE_TZ", "America/New_York"))
STATS_DIR = Path(os.environ.get("STATS_DIR", "/tmp/kidsdaily-stats"))
STATS_DIR.mkdir(parents=True, exist_ok=True)

ENABLED = os.environ.get("ANALYTICS", "on").strip().lower() not in ("off", "0", "false")

# Anything not in here is dropped, so a stray POST can't bloat the log.
EVENT_TYPES = {
    "view", "session", "reveal", "joke_reveal", "wordle_result",
    "conn_result", "link_click", "age_switch",
}
SECTIONS = {
    "s-news", "s-sports", "s-word", "s-brain", "s-wordle",
    "s-conn", "s-history", "s-joke", "s-story",
}
SECTION_LABELS = {
    "s-news": "Today's News",
    "s-sports": "Sports",
    "s-word": "Word of the Day",
    "s-brain": "Brain Teasers",
    "s-wordle": "Guess the Word",
    "s-conn": "Make Four Groups",
    "s-history": "On This Day",
    "s-joke": "Joke of the Day",
    "s-story": "Story of the Day",
}

_LOCK = threading.Lock()
_last_push = 0.0
PUSH_EVERY = 300  # seconds


def today() -> date:
    return datetime.now(TZ).date()


def _path(day: date) -> Path:
    return STATS_DIR / f"{day.isoformat()}.jsonl"


# --------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------

def _clean_event(raw: dict) -> dict | None:
    """Validate and normalise one event. Returns None if it should be dropped."""
    if not isinstance(raw, dict):
        return None
    etype = str(raw.get("type", ""))[:24]
    if etype not in EVENT_TYPES:
        return None

    ev: dict[str, Any] = {"type": etype, "ts": datetime.now(TZ).isoformat()}

    age = str(raw.get("age", ""))[:2]
    ev["age"] = age if age in ("9", "11") else "?"

    section = str(raw.get("section", ""))[:32]
    if section:
        ev["section"] = section if section in SECTIONS else "other"

    # seconds: clamp hard. A backgrounded tab or a hand-crafted POST should not
    # be able to claim six hours on the joke.
    try:
        secs = float(raw.get("seconds", 0) or 0)
    except (TypeError, ValueError):
        secs = 0.0
    if secs > 0:
        ev["seconds"] = round(min(max(secs, 0.0), 3600.0), 1)

    for key, cast, cap in (("guesses", int, 10), ("mistakes", int, 10)):
        if raw.get(key) is not None:
            try:
                ev[key] = min(max(cast(raw[key]), 0), cap)
            except (TypeError, ValueError):
                pass
    if raw.get("won") is not None:
        ev["won"] = bool(raw["won"])
    if raw.get("solved") is not None:
        ev["solved"] = bool(raw["solved"])

    for key in ("puzzle", "domain", "sid"):
        if raw.get(key):
            ev[key] = str(raw[key])[:64]
    return ev


def record(events: list[dict]) -> int:
    """Append a batch of events. Returns how many were kept."""
    if not ENABLED:
        return 0
    cleaned = [e for e in (_clean_event(r) for r in (events or [])[:200]) if e]
    if not cleaned:
        return 0
    day = today()
    with _LOCK:
        try:
            with _path(day).open("a", encoding="utf-8") as fh:
                for ev in cleaned:
                    fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001 - tracking must never break the page
            log.exception("could not write analytics")
            return 0
    _maybe_push(day)
    return len(cleaned)


# --------------------------------------------------------------------------
# persistence (optional, but required for stats to outlive a restart)
# --------------------------------------------------------------------------

def _repo() -> tuple[str, str] | None:
    repo = os.environ.get("STATS_DATASET_REPO") or os.environ.get("CACHE_DATASET_REPO")
    token = os.environ.get("HF_TOKEN")
    return (repo, token) if repo and token else None


def _maybe_push(day: date, force: bool = False) -> None:
    global _last_push
    if not _repo():
        return
    if not force and time.time() - _last_push < PUSH_EVERY:
        return
    _last_push = time.time()
    threading.Thread(target=_push, args=(day,), daemon=True).start()


def _push(day: date) -> None:
    creds = _repo()
    if not creds or not _path(day).exists():
        return
    repo, token = creds
    try:
        from huggingface_hub import HfApi

        HfApi(token=token).upload_file(
            path_or_fileobj=str(_path(day)),
            path_in_repo=f"stats/{day.isoformat()}.jsonl",
            repo_id=repo,
            repo_type="dataset",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("stats push failed: %s", exc)


def restore(days: int = 60) -> int:
    """Pull previous days back from the dataset after a restart."""
    creds = _repo()
    if not creds:
        return 0
    repo, token = creds
    restored = 0
    try:
        from huggingface_hub import hf_hub_download

        for i in range(days):
            d = today() - timedelta(days=i)
            if _path(d).exists():
                continue
            try:
                src = hf_hub_download(
                    repo_id=repo, filename=f"stats/{d.isoformat()}.jsonl",
                    repo_type="dataset", token=token,
                )
                _path(d).write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8")
                restored += 1
            except Exception:  # noqa: BLE001 - that day simply doesn't exist
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("stats restore failed: %s", exc)
    if restored:
        log.info("restored %d days of stats", restored)
    return restored


def flush() -> None:
    _maybe_push(today(), force=True)


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# feedback
# --------------------------------------------------------------------------
# Deliberately write-only from the page. The site is public, so anything shown
# back to visitors would be an open comment board on a children's site. Notes
# go straight to the parent dashboard and nowhere else.

MAX_MESSAGE = 1000
MAX_PER_DAY = 500
RATINGS = {"love", "ok", "meh"}


def _feedback_path(day: date) -> Path:
    return STATS_DIR / f"feedback-{day.isoformat()}.jsonl"


def record_feedback(raw: dict) -> bool:
    if not isinstance(raw, dict):
        return False
    rating = str(raw.get("rating", ""))[:8]
    message = str(raw.get("message", "") or "").strip()[:MAX_MESSAGE]
    favourite = str(raw.get("favourite", ""))[:32]
    if not message and rating not in RATINGS:
        return False  # nothing of substance

    day = today()
    path = _feedback_path(day)
    try:
        if path.exists() and sum(1 for _ in path.open(encoding="utf-8")) >= MAX_PER_DAY:
            return False
    except Exception:  # noqa: BLE001
        pass

    age = str(raw.get("age", ""))[:2]
    entry = {
        "ts": datetime.now(TZ).isoformat(),
        "age": age if age in ("9", "11") else "?",
        "rating": rating if rating in RATINGS else None,
        "favourite": SECTION_LABELS.get(favourite, favourite or None),
        "message": message,
    }
    # Flag rather than hide: this is the parent's inbox, and a public endpoint
    # means a stranger could in principle post. Better to see it, marked.
    try:
        import safety

        if message and not safety.is_safe(message):
            entry["flagged"] = True
    except Exception:  # noqa: BLE001
        pass

    with _LOCK:
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            log.exception("could not write feedback")
            return False
    _push_feedback(day)
    return True


def _push_feedback(day: date) -> None:
    creds = _repo()
    if not creds or not _feedback_path(day).exists():
        return
    repo, token = creds

    def _go():
        try:
            from huggingface_hub import HfApi

            HfApi(token=token).upload_file(
                path_or_fileobj=str(_feedback_path(day)),
                path_in_repo=f"feedback/{day.isoformat()}.jsonl",
                repo_id=repo, repo_type="dataset",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("feedback push failed: %s", exc)

    threading.Thread(target=_go, daemon=True).start()


def read_feedback(days: int = 60) -> list[dict]:
    out: list[dict] = []
    for i in range(days):
        d = today() - timedelta(days=i)
        p = _feedback_path(d)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                entry["day"] = d.isoformat()
                out.append(entry)
            except json.JSONDecodeError:
                continue
    return sorted(out, key=lambda e: e.get("ts", ""), reverse=True)


def restore_feedback(days: int = 60) -> int:
    creds = _repo()
    if not creds:
        return 0
    repo, token = creds
    n = 0
    from_hub = None
    try:
        from huggingface_hub import hf_hub_download
        from_hub = hf_hub_download
    except Exception:  # noqa: BLE001
        return 0
    for i in range(days):
        d = today() - timedelta(days=i)
        if _feedback_path(d).exists():
            continue
        try:
            src = from_hub(repo_id=repo, filename=f"feedback/{d.isoformat()}.jsonl",
                           repo_type="dataset", token=token)
            _feedback_path(d).write_text(Path(src).read_text(encoding="utf-8"), encoding="utf-8")
            n += 1
        except Exception:  # noqa: BLE001
            continue
    return n


def _read_day(day: date) -> list[dict]:
    p = _path(day)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def available_days() -> list[date]:
    days = []
    for p in STATS_DIR.glob("*.jsonl"):
        try:
            days.append(date.fromisoformat(p.stem))
        except ValueError:
            continue
    return sorted(days)


def summarise(events: list[dict]) -> dict:
    """Turn raw events into the numbers the dashboard shows."""
    section_secs: dict[str, float] = defaultdict(float)
    section_secs_by_age: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    sessions: set[str] = set()
    total_secs = 0.0
    reveals: dict[str, int] = defaultdict(int)
    jokes = 0
    links: dict[str, int] = defaultdict(int)
    wordle = {"played": 0, "won": 0, "guesses": []}
    conn = {"played": 0, "solved": 0, "mistakes": []}
    age_seen: dict[str, int] = defaultdict(int)

    for e in events:
        t = e.get("type")
        age = e.get("age", "?")
        if e.get("sid"):
            sessions.add(e["sid"])
        if t == "view":
            s = e.get("section", "other")
            secs = float(e.get("seconds", 0) or 0)
            section_secs[s] += secs
            section_secs_by_age[s][age] += secs
            age_seen[age] += 1
        elif t == "session":
            total_secs += float(e.get("seconds", 0) or 0)
        elif t == "reveal":
            reveals[e.get("puzzle", "?")] += 1
        elif t == "joke_reveal":
            jokes += 1
        elif t == "link_click":
            links[e.get("domain", "?")] += 1
        elif t == "wordle_result":
            wordle["played"] += 1
            if e.get("won"):
                wordle["won"] += 1
                if e.get("guesses"):
                    wordle["guesses"].append(int(e["guesses"]))
        elif t == "conn_result":
            conn["played"] += 1
            if e.get("solved"):
                conn["solved"] += 1
            if e.get("mistakes") is not None:
                conn["mistakes"].append(int(e["mistakes"]))

    ranked = sorted(section_secs.items(), key=lambda kv: kv[1], reverse=True)
    grand = sum(section_secs.values()) or 1.0

    return {
        "sessions": len(sessions),
        "total_seconds": round(total_secs or sum(section_secs.values()), 1),
        "sections": [
            {
                "id": sid,
                "label": SECTION_LABELS.get(sid, sid),
                "seconds": round(secs, 1),
                "share": round(100 * secs / grand, 1),
                "by_age": {a: round(v, 1) for a, v in section_secs_by_age[sid].items()},
            }
            for sid, secs in ranked
        ],
        "answers_revealed": dict(reveals),
        "jokes_revealed": jokes,
        "link_clicks": dict(sorted(links.items(), key=lambda kv: -kv[1])),
        "wordle": {
            "played": wordle["played"],
            "won": wordle["won"],
            "avg_guesses": round(sum(wordle["guesses"]) / len(wordle["guesses"]), 1)
            if wordle["guesses"] else None,
        },
        "connections": {
            "played": conn["played"],
            "solved": conn["solved"],
            "avg_mistakes": round(sum(conn["mistakes"]) / len(conn["mistakes"]), 1)
            if conn["mistakes"] else None,
        },
        "age_activity": dict(age_seen),
    }


def daily(day: date | None = None) -> dict:
    day = day or today()
    s = summarise(_read_day(day))
    s["date"] = day.isoformat()
    return s


def overall(limit_days: int = 120) -> dict:
    days = available_days()[-limit_days:]
    everything: list[dict] = []
    series = []
    for d in days:
        evs = _read_day(d)
        everything.extend(evs)
        one = summarise(evs)
        series.append({
            "date": d.isoformat(),
            "seconds": one["total_seconds"],
            "sessions": one["sessions"],
            "top": one["sections"][0]["label"] if one["sections"] else None,
        })
    total = summarise(everything)
    total["days_tracked"] = len(days)
    total["first_day"] = days[0].isoformat() if days else None
    total["last_day"] = days[-1].isoformat() if days else None
    total["series"] = series
    total["persistent"] = bool(_repo())
    return total
