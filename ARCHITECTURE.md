# Kids Daily — How It Works, Front to Back

A single web page that rebuilds itself once a day with news, puzzles, games and
a good story, tuned for a 9-year-old and an 11-year-old. Live at
`ksisters.onrender.com`.

This document explains the whole system: the stack, what happens when a browser
asks for the page, how a day gets built, and why several non-obvious decisions
were made the way they were.

---

## 1. The stack, and why each piece

| Layer | Choice | Why this one |
|---|---|---|
| Web framework | **FastAPI** (`0.115.6`) | Async, tiny, JSON-first. The whole API is 12 routes; a heavier framework would be scaffolding around nothing. |
| Server | **uvicorn** (`0.34.0`) | What FastAPI expects. Must bind Render's `$PORT`. |
| Hosting | **Render**, free plan | The last host with a genuine free tier for a Python web service. HuggingFace Spaces was the original plan until compute Spaces went paid. |
| Content generation | **Anthropic API**, `claude-sonnet-5` | Two calls per day. One for puzzles and creative content, one to rewrite news for children. |
| HTTP client | **httpx** (`0.28.1`) | Fetching 20+ RSS feeds. Sync client, per-request timeout. |
| Feed parsing | **`xml.etree.ElementTree`** (stdlib) | RSS 2.0 and Atom only. No dependency needed for two formats. |
| Persistence | **HuggingFace Datasets** (private) | Render's free plan has no disk. HF datasets are still free even though Spaces are not. Holds the cached day *and* the engagement log. |
| Frontend | **Vanilla JS, one file** | No build step, no framework, no `node_modules`. The page is a document with four games in it. |
| Fonts | Google Fonts (Outfit + Inter) | The only third-party asset on the page. |
| Scheduling | **cron-job.org** | Pings `/ping` every 10 min, 5:45am–9:00pm, to stop the free instance sleeping. |

Total runtime dependencies: **five**. That is deliberate — this has to run
unattended for a month with nobody maintaining it.

---

## 2. The shape of it

```
                    ┌──────────────────────────────────────┐
   cron-job.org ───►│  GET /ping        (14 bytes)         │
   every 10 min     │  keeps the free instance awake       │
                    └──────────────┬───────────────────────┘
                                   │ if today isn't cached,
                                   │ start a build on a thread
                                   ▼
 ┌────────────┐   GET /      ┌─────────────────┐
 │  Browser   │─────────────►│                 │      ┌─────────────────┐
 │ (iPad,     │              │    FastAPI      │─────►│  8 RSS feed     │
 │  laptop)   │  GET         │    app.py       │      │  groups (20+    │
 │            │  /api/today  │                 │      │  URLs)          │
 │            │◄─────────────│                 │      └─────────────────┘
 │            │   one JSON   │   builder.py    │      ┌─────────────────┐
 │            │   payload    │   the pipeline  │─────►│  Wikimedia      │
 │            │              │                 │      │  On This Day    │
 │  app.js    │  POST        │                 │      └─────────────────┘
 │  renders   │  /api/track  │                 │      ┌─────────────────┐
 │  + 4 games │─────────────►│                 │─────►│  Anthropic API  │
 └────────────┘              └────────┬────────┘      │  2 calls/day    │
                                      │               └─────────────────┘
                                      ▼
                            ┌──────────────────────┐
                            │  /tmp (ephemeral)    │
                            │  mirrored to a       │
                            │  private HF dataset  │
                            └──────────────────────┘
```

---

## 3. What happens when a browser opens the page

1. `GET /` → `app.py` returns `static/index.html`. Static skeleton, no content.
2. The browser loads `style.css` and `app.js`.
3. `app.js` fires `fetch("/api/today")`.
4. `app.py` calls `builder.get_day()`:
   - **cache hit** on local disk → return immediately
   - **miss** → try the HuggingFace dataset
   - **still nothing** → take a lock and build the day (20–40 s, one time)
5. Before responding, `_hide_answers()` base64-encodes the Wordle words, puzzle
   answers, joke punchline and Sudoku solutions.
6. `app.js` receives one JSON blob and renders every section from it.

**One payload, one round trip.** No per-section endpoints, no loading spinners
per card. The page either has today or it does not.

The base64 is **obfuscation, not security** — it exists so that an 11-year-old
who opens the network tab does not get the Wordle answer handed to her. Anyone
who knows what `atob` is can read it in five seconds. That is the intended level
of difficulty.

---

## 4. Building a day

`builder.build()` — this is the heart of the system.

```
 1. Wikimedia On This Day        →  raw historical events
 2. safety.scrub_events()        →  drop anything unsuitable      [SAFETY 1]
 3. recent_signatures()          →  what news ran in the last 7 days
    recent_creative()            →  puzzles/jokes/words from the last 21 days
 4. fetch_all_feeds()            →  8 sections, multi-feed merged, deduped
 5. prefer_fresh()               →  tiered: unseen > new URL > anything
 6. safety.filter_items()        →  blocklist per section           [SAFETY 2]
 7. llm.generate_creative()      →  puzzles, word, joke, groups, history
    llm.edit_news()              →  rewrite headlines for children
 8. _merge_creative/_merge_news  →  validate; bank-swap failures    [SAFETY 3]
 9. _dedupe_creative()           →  swap anything already used
10. sudoku.daily()               →  generated algorithmically, not by the model
11. _write_cache() + _push_to_hub()
```

### Step 5 is subtler than it looks

`prefer_fresh()` is a *preference*, not a filter. It returns the best tier
available:

| Tier | Meaning |
|---|---|
| `fresh` | Never-before-seen headline and URL |
| `new_url` | Headline seen before, different article |
| `any` | Everything, repeats included |

An earlier version dropped repeats outright. On day two the Eagles, NFL, tennis
and cricket sections all rendered **empty**, because those feeds barely move
overnight. A stale headline beats a blank card. `freshness_relaxed` in `/health`
names any section that had to fall back.

### Step 8 is where things quietly go wrong

Every model output is structurally validated before it can reach the page:

- Connections must have exactly 16 **distinct** words in 4 groups of 4 — a
  repeated tile makes the game literally unwinnable
- Wordle words must be exactly 5 ASCII letters and pass the profanity check
- Puzzles need both a question and an answer at both levels
- The feel-good story must be at least 400 characters

Anything failing validation is replaced from `fallback.py`, an offline bank of
hand-written content (21 maths pairs, 21 logic pairs, 40 jokes, 92 Wordle words,
6 Connections boards). `fell_back_to_bank` in `/health` lists what was replaced.

**This is the mechanism that hid a bug for a week.** If the model's response is
truncated, `_salvage_json` recovers the largest valid prefix — the first two
sections — and the remaining five fall back to the bank *while the log still
says "claude ok"*. That is now caught: any response missing a key from
`CREATIVE_KEYS` is retried once and, if still short, reported as
`[incomplete: ...]`.

---

## 5. The content day is not the calendar day

`DAY_ROLLOVER_HOUR=20`. At 8pm local, `builder.today()` starts returning
*tomorrow's* date, and an entirely new page goes live: new puzzles, new Wordle,
new news.

The reasoning: the girls often play after dinner, and a page that changes at
midnight means the evening session and the next morning's session are the same
content. Rolling over at 8pm gives the evening its own page.

This caused a genuine confusion — the 9-year-old reported getting "the same
wordle as yesterday". She had not. She played at 8:30pm (already tomorrow's
page) and again the next morning (still the same content day). The page now says
so explicitly in the header when it is running ahead of the wall clock.

**Analytics deliberately stay on calendar days.** Engagement questions are asked
in ordinary human terms, so "today" in the stats dashboard means today.

`SITE_TZ=America/New_York`, so this tracks the EDT/EST switch — it is 8pm all
year, not 8pm EST drifting to 7pm.

---

## 6. Safety: four layers

The requirement was blunt: *only kid-appropriate content, from all external
sources.* No single check is trusted.

### Layer 1 — the blocklist (`safety.py`)

~2,300 word forms and 137 phrases across violence, crime, abuse, substances,
adult content, profanity and slurs.

The key design decision is **stem-based inflection**. `_forms("stab")` generates
`stabs, stabbed, stabbing, stabbings, stabber, stabbers…` including
doubled-consonant forms. The first version matched whole words only, and **18 of
20 realistic bad headlines got through** because it blocked `shooting` but not
`shootings`. The generator deliberately over-generates: a spurious extra form
costs a dropped headline, a missing one costs a bad headline in front of a child.

`_normalise()` first defeats evasion — `p0rn` → `porn`, `f.u.c.k` → `fuck`,
`sh!t` → `shit`.

**Two strictness tiers:**

- `level="news"` — untrusted feed and model output. Blunt: drops anything near a
  hard topic, including gentle mentions of death, because framing is unknowable.
- `level="curated"` — hand-written bank text. Blocks explicit material, but
  permits a story where an elderly regular passes away and his friends keep his
  table free. Refusing to let children encounter death in any form is not
  safety, it is avoidance — and a person has already checked the framing.

**Sports mode** blanks ~62 phrases that are violent-sounding but routine in a
match report (`sudden death`, `shootout`, `crushed the`) before running the
blocklist, so the Eagles section is not deleted by its own vocabulary.

### Layer 2 — a positive gate for local news

A blocklist asks "does this contain something bad?" For a small-town feed that
is not enough: local news is mostly police blotter and zoning disputes, and
plenty of it is unsuitable without tripping any keyword — *"Man, 34, charged
following incident on Route 571"*.

So local items must **also** positively match one of 74 `LOCAL_TOPICS` (school,
festival, park, team, award…). An empty local section is a perfectly good
outcome; a police report is not. This is why `westwindsor` is often empty and
why it is on the `OPTIONAL` list rather than flagging the site degraded.

### Layer 3 — the model's editorial instructions

`HOUSE_RULES` in `llm.py`, including an explicit untrusted-input block: feed
content arrives wrapped in `<feed_data>` delimiters with angle brackets
stripped, and the model is told that nothing inside is an instruction. That is
prompt-injection hardening — an RSS title is attacker-controlled text.

### Layer 4 — outbound links

The one place the kids leave the safe zone. A link survives only if it is
`https` **and** its domain is on a 49-entry allowlist. `javascript:` and `data:`
are blocked server-side *and* again client-side in `safeHref()`. `news.google.com`
is deliberately excluded — it is a redirect to a publisher nobody vetted.

Links carry `rel="noopener noreferrer nofollow"` and `referrerPolicy="no-referrer"`.

---

## 7. Not repeating yourself

Three separate mechanisms, because they guard different things.

**News** — `recent_signatures()` reads the last 7 days of cached payloads and
builds sets of headline signatures and URLs.

**Creative content** — `recent_creative()` reads back **21 days** for Wordle
words, words of the day, jokes, Connections category names, and (as of this
week) maths and logic puzzles.

**Signature choice matters.** News uses `_sig()` — strip everything
non-alphanumeric, truncate. Jokes and puzzles use `_wordkey()` — drop filler
words, keep numbers, sort what remains. The difference is the whole game:

```
_sig     ("Why did the math book look sad?")  ≠ _sig     ("...look SO sad?")
_wordkey ("Why did the math book look sad?")  = _wordkey ("...look SO sad?")
```

The joke was slipping past the repeat check on a single extra word.

**Two lines of defence.** The list of recently-used items is sent to the model
so it steers away up front; then `_dedupe_creative()` swaps anything that still
comes back as a repeat with an unused bank entry.

**Rotating the required form** is the part that actually fixed the sameness. Each
day the prompt demands a specific *kind* of puzzle — 11 logic styles, 9 maths
topics, 7 joke types, indexed by date ordinal. Left alone, the model reaches for
the same classics; the clock with hands showed up three days running. Those
specific chestnuts are now banned by name in the prompt.

---

## 8. Sudoku is not generated by the model

`sudoku.py` is the one piece of content deliberately kept away from Claude. A
Sudoku is only a real puzzle if it has exactly one solution, and that is not a
guarantee you get by asking nicely.

```
build a complete valid grid   (randomised backtracking, seeded from the date)
remove clues in pairs         (symmetric, like a newspaper puzzle)
  keep a removal ONLY IF:
    the puzzle still has exactly one solution     (solution counting, limit=2)
    AND it is still solvable by singles alone     (solve_with_singles)
```

Starting from a full grid — trivially singles-solvable — and only ever removing
while both properties hold means **the no-guessing promise is true by
construction**, not by testing afterwards.

"Solvable by singles" means only two techniques are ever required:

- **naked single** — this cell has one possible digit
- **hidden single** — this digit has one possible home in its row, column or box

No candidate-pair reasoning, no trial and error. This matters more than clue
count. The 11-year-old originally found the 9×9 "too difficult" at 38 clues, not
because 38 is few but because the puzzle demanded techniques nobody had taught
her. At 44 clues *with the singles guarantee* it works.

Current settings, measured rather than guessed:

| Level | Grid | Clues | Deductions |
|---|---|---|---|
| Age 9 | 6×6, 2×3 boxes | 12 | ~24 |
| Age 11 | 9×9, 3×3 boxes | 44 | ~37 |

Below about 12 clues a 6×6 stops having a unique singles-solvable puzzle at all,
so 12 is a measured floor, not a preference. That is why the Sudoku card has its
own **6×6 / 9×9** switch — when a 6×6 is outgrown, the answer is a bigger grid,
not fewer clues.

Everything is seeded from `f"kidsdaily-{date}-{size}"`, so both kids get the
same puzzle all day and it changes overnight. No API cost, no failure mode, no
network.

---

## 9. Storage on a host with no disk

Render's free plan wipes the filesystem every time the service sleeps.

```
/tmp/kidsdaily/2026-08-08.json          the built day
/tmp/kidsdaily-stats/2026-08-08.jsonl   engagement events
```

Both are mirrored to a **private HuggingFace dataset**. On boot, `restore()`
pulls the last 60 days back; `get_day()` checks local disk, then the dataset,
then builds.

Without this: the day gets rebuilt after every sleep (roughly 4¢ instead of 2¢,
trivial) — but more importantly the 21-day creative memory and the entire
engagement history would reset nightly, so the anti-repeat logic would have
nothing to compare against.

Stats are pushed at most once every 5 minutes and again on shutdown, using
Render's spin-down grace period.

---

## 10. The frontend

`static/app.js` — one 1,160-line IIFE, no framework, no build step.

**State lives in `localStorage`**, namespaced by content date:

```
kd-2026-08-08-wordle-easy     board state
kd-2026-08-08-sudoku-hard     grid state
kd-streak-wordle              { last, streak, best }
kd-age                        which level is selected
kd-sd-level                   Sudoku grid override
kd-journal                    the check-in scrapbook
```

Every access goes through `lsGet`/`lsSet` wrappers, because Safari private mode
throws on any `localStorage` access and an unguarded call blanks the page.

**Consequences worth knowing:** streaks are per-browser, so a shared laptop
means a shared streak. The age toggle sets puzzle difficulty, not identity.

**Two independent difficulty controls**, deliberately:

- the **age toggle** in the header changes puzzles, Wordle and Sudoku together
- the **6×6 / 9×9 buttons** in the Sudoku card override just that game

A child outgrowing one game should not have to change everything else.

**The keyboard bug worth remembering.** The Wordle key handler was bound to the
whole document with no check on where the keystroke was going. Every letter typed
into the Summer Check-In box also landed in the Wordle row. Five characters
later the row was full and every real guess was silently dropped — which from
the other side of the screen looks exactly like *"I can't type."* It now ignores
anything typed into an `input`, `textarea`, `select` or contenteditable.

---

## 11. Engagement tracking

**Recorded:** how long each section was on screen with the tab focused, which
puzzles were opened, game results, link click-throughs, age-toggle switches.

**Not recorded:** no names, no accounts, no IP addresses, no cookies, nothing
they type, not their guesses. The session id is random and dies with the tab.

Time is attributed by `IntersectionObserver` to whichever section the scrollspy
considers active, so two sections visible on a wide screen do not both bank the
seconds. `visibilitychange` pauses the clock when the tab is backgrounded.

Server side, `_clean_event()` is a strict whitelist: unknown event types are
dropped, unknown sections become `"other"`, and every numeric field is clamped —
a hand-crafted POST cannot claim six hours on the joke.

The parent dashboard is at `/stats?token=…`, with Today and All-time tabs, split
by which age level was selected. It is a proxy for which kid, not an identity.

---

## 12. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | — | The page |
| GET/POST/HEAD/PUT | `/ping` | — | 14 bytes. Keep-alive. Any method, on purpose. |
| GET | `/api/today` | — | Today's payload, answers encoded |
| GET | `/api/day/{date}` | — | An archived day |
| GET | `/health` | — | Full diagnostics; `?brief=1` for 138 bytes |
| POST | `/api/refresh` | token | Force a rebuild; returns 202, builds on a thread |
| GET | `/api/refresh/status` | token | How that rebuild is going |
| POST | `/api/track` | — | Engagement events |
| POST | `/api/feedback` | — | A note from the kids |
| POST | `/api/journal` | — | The Summer Check-In |
| GET | `/stats` | token | Parent dashboard |
| GET | `/api/stats.json` | token | The same data as JSON |

`/ping` and `/health` are split for a reason: `/health` grew a full diagnostics
block, and cron-job.org aborts any response over **64 KB** and returns
*"output too large"*. A monitoring endpoint should say as little as possible.
`/ping` also answers to any HTTP verb, because a keep-alive that returns 405
over a verb choice is a failure with no upside.

---

## 13. Configuration

| Variable | Default | Effect |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Without it, everything comes from the offline bank |
| `ADMIN_TOKEN` | — | Guards `/stats` and `/api/refresh` |
| `HF_TOKEN` + `CACHE_DATASET_REPO` / `STATS_DATASET_REPO` | — | Persistence across sleeps |
| `DAY_ROLLOVER_HOUR` | `0` | Set to `20`: next day's page at 8pm |
| `SITE_TZ` | `America/New_York` | Rollover tracks the local clock |
| `LINKS_MODE` | `allowlist` | `off` removes all outbound links |
| `ANALYTICS` | `on` | `off` disables tracking entirely |
| `CLAUDE_MODEL` | `claude-sonnet-5` | |

---

## 14. What happens when things fail

| Failure | Result |
|---|---|
| An RSS feed is down | Other feeds in that group cover it; `/health` names it |
| All feeds for a section fail | Claude web-search fallback, then the bank |
| Wikimedia is down | Claude supplies events from its own knowledge |
| Claude returns malformed JSON | `_salvage_json` recovers the valid prefix; retry once; bank fills the rest |
| Claude is unreachable | The whole page comes from `fallback.py` — still a complete, safe day |
| No API key at all | Same as above, permanently |
| Render sleeps | ~1 min cold start; the keep-alive cron mostly prevents it |
| Nothing new in a feed | `prefer_fresh` relaxes rather than render a blank card |
| Safety filter thins the history | Topped up from Wikipedia's own wording |

The design rule throughout: **degrade to duller, never to broken, and never to
unsafe.**

---

## 15. Cost

Two Anthropic calls per day, roughly 2–4¢. Under **$2 for a 30-day summer**.
Render free, HuggingFace datasets free, cron-job.org free.

The spend cap in the Anthropic console is the real safety net — if it is ever
hit, the site falls back to the bank rather than breaking.

---

## 16. File map

| File | Lines | What it is |
|---|---|---|
| `app.py` | 335 | FastAPI routes, answer encoding, background rebuilds |
| `builder.py` | 737 | The pipeline: validate, merge, de-duplicate, cache |
| `llm.py` | 523 | Two Claude calls, prompts, house rules, JSON salvage |
| `safety.py` | 452 | Blocklist, inflection generator, URL allowlist, local gate |
| `fallback.py` | 531 | The offline content bank |
| `sources.py` | 243 | RSS and Wikimedia fetching |
| `analytics.py` | 620 | Event recording, feedback, journal, aggregation |
| `sudoku.py` | 280 | Algorithmic generator with the singles guarantee |
| `static/app.js` | 1,160 | Rendering, four games, streaks, tracking |
| `static/style.css` | 797 | Mt. Titlis hero, cards, responsive layout |
| `static/index.html` | 308 | Section skeleton |
| `static/stats.html` | 317 | Parent dashboard |

---

## 17. If you extend it

- **A new content section:** add the source to `sources.py`, a validator to
  `builder.py`, a bank entry to `fallback.py`, a section to `index.html`, a
  renderer to `app.js`, and the section id to `analytics.SECTIONS`. That last
  one is easy to forget — `s-summer` was, and its time is bucketed as "other".
- **A new tracked interaction:** add the event type to `analytics.EVENT_TYPES`
  in the same commit as the `TRACK.push` in `app.js`. Unknown types are dropped
  silently, which has already happened twice.
- **Changing difficulty:** see the table in `DEPLOY.md`. Each knob is one number.
- **Retiring it:** delete the Render service, the cron job, and the HF dataset,
  and rotate `ADMIN_TOKEN`.
