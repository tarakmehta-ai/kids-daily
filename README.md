# Kids Daily

A website that rebuilds itself every morning for two kids (9 and 11).

Runs as a FastAPI app on **Render's free plan** — see `DEPLOY.md`. A
`Dockerfile` is included for any Docker-capable host; note that HuggingFace
Spaces now requires a paid plan for anything that runs compute.

## What's on the page

| Section | Where it comes from |
|---|---|
| Today's news | BBC Newsround RSS, rewritten for kids by Claude |
| Sports: Eagles / NFL / tennis / Indian cricket | Publisher RSS per topic (BGN, BBC Sport, ESPNcricinfo), rewritten by Claude |
| Around West Windsor | Local NJ feeds, filtered hard (see below) |
| Word of the day | Claude |
| Math + logic puzzles | Claude, at two difficulty levels (age 9 / age 11 toggle) |
| Guess the Word | Our own Wordle-style game. Two word tiers (age 9 / age 11), the clue is hidden behind a button, and solving reveals a fact about the word plus a shareable emoji grid |
| Make Four Groups | Our own Connections-style grid |
| Sudoku | Generated algorithmically in `sudoku.py` — 6x6 for age 9, 9x9 for age 11, uniqueness proved before it ships |
| On this day | Wikimedia On-This-Day API, retold by Claude |
| Joke | Claude |
| Story of the day | A real feel-good news story, or a story from the offline bank |
| Feedback | A note from the kids, stored for the parent dashboard |

## How the daily refresh works

**Set to roll over at 8pm** (`DAY_ROLLOVER_HOUR=20`): at 8pm local time the site
starts serving the *next* day's page — new puzzles, new Wordle, new joke, new
news — and the date in the header reads tomorrow. It stays on that page until
8pm the following evening, so nothing changes under the kids overnight or
during the day.

This shifts the **content** day only. Analytics stay on calendar days, so the
evening summary still means "what happened today" in the ordinary sense.

The first visit of each content day triggers a build: fetch the feeds,
filter them for age-appropriateness, then two Claude calls — one for the
creative content, one to turn real headlines into kid-readable summaries. The
result is cached, so every later visit that day is instant and free.

If a feed is down, Claude's web search fills the gap. If Claude is unavailable,
`fallback.py` supplies a puzzle, joke, word and story from an offline bank. The
page never shows an error.

## The hero image

`static/hero.jpg` is a family photo from Mount Titlis, looking down over
Trubsee lake. Two derived files sit beside it:

- `hero-blur.jpg` — a 480px pre-blurred copy used for the fixed page backdrop.
  Blurring a 2000px image live costs real frames on a phone; this doesn't.
- `hero.svg` — an illustrated alpine fallback, kept in case you ever want it.

The scrim gradient over the photo was tuned against its actual pixels: white
title text clears WCAG AA (worst case 5.1:1) at every viewport width tested.
**If you replace the photo, re-check that** — see the comment at the top of
`static/style.css` for the regeneration command and the `--hero-y` focal point
control.

## Configuration

Set these in your host's environment settings (Render → Environment):

| Name | Type | Required | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | secret | yes | Generates the daily content |
| `ADMIN_TOKEN` | secret | no | Lets you force a rebuild via `POST /api/refresh?token=…` |
| `CACHE_DATASET_REPO` | variable | no | e.g. `you/kids-daily-cache` — persists the cache so a Space restart doesn't re-generate (and re-bill) the day |
| `HF_TOKEN` | secret | no | Write token, needed only for `CACHE_DATASET_REPO` |
| `PORT` | variable | no | Set by the host. Render assigns it; don't hardcode it |
| `STATS_DATASET_REPO` | variable | no | HF dataset for the engagement log. **Required for stats to survive a restart** |
| `ANALYTICS` | variable | no | `on` by default; set `off` to disable tracking |
| `SITE_TZ` | variable | no | Defaults to `America/New_York` |
| `DAY_ROLLOVER_HOUR` | variable | no | Hour (0-23, local) when the next day's page goes live. `20` = 8pm. `0`/unset = midnight |
| `CLAUDE_MODEL` | variable | no | Defaults to `claude-sonnet-5` |
| `LINKS_MODE` | variable | no | `allowlist` (default), `off`, or `all` — see below |

### `LINKS_MODE`

**Default is `allowlist`.** A "Read the full story" link appears only when the
URL points at a domain in `safety.ALLOWED_LINK_DOMAINS`. That list is headed by
the four sites you asked for — **BBC, ESPN, ESPNcricinfo and Bleeding Green
Nation** — followed by other vetted outlets (Reuters, NPR, NASA, Cricbuzz and
so on). Delete any of those extras you don't want; nothing depends on them.

Because links are useful again, the feed order in `sources.py` now puts direct
publisher feeds first: Bleeding Green Nation leads the Eagles section, ESPN
leads tennis, ESPNcricinfo leads cricket. Google News sits behind them as a
coverage fallback, and **its links are always stripped** — they redirect
through `news.google.com` to a publisher nobody has vetted. A story that came
from the fallback appears without a link. That is expected, not a bug.

Other modes:

- **`off`** — no outbound links at all. Summaries only; the kids never leave.
- **`all`** — any `https` link. Still blocks `javascript:` and `data:`, but you
  are trusting the open web. Prefer widening the allowlist instead.

In every mode `javascript:`, `data:` and plain `http:` are refused on the
server and refused again in the browser. `/health` reports the active mode.

**One caveat about Bleeding Green Nation.** It is an SB Nation fan blog, not a
newsroom like the BBC. The reporting is solid and its headlines pass through
exactly the same safety filter as every other source, but fan-blog articles
carry comment threads, and comment threads are not moderated to a 9-year-old's
standard. The filter cannot see them. Worth knowing before they click through.

## No repeats across days (without blank sections)

`builder.recent_signatures()` reads the previous 7 cached days and collects
every headline signature and link already used. Those are listed in the prompt
as "already used", and `prefer_fresh()` applies them in **tiers** at both the
feed stage and the model-output stage:

1. items never seen before — ideal
2. failing that, items whose **URL** is new (headline may be similar)
3. failing that, everything — a stale card beats a blank one

This started life as a hard filter and blanked all four sports sections on day
two: those feeds barely move, so once the previous day had used the top
stories, everything remaining looked like a repeat. Freshness is a preference
now, never a guillotine. `/health` reports `freshness_relaxed` naming any
section that had to drop a tier.

Feeds also **aggregate** rather than first-wins: `sources.fetch_feed()` merges
items from every candidate feed for a topic, de-duplicated, up to 20. Eagles
now draws on six feeds rather than one, which is what makes tier 1 achievable
most days.

The feel-good story has an extra bar: it must be at least 700 characters and
come from a dedicated good-news outlet (Good News Network, Positive News,
Reasons to be Cheerful) rather than a Google News query. The prompt requires
named people and a named place, and explicitly permits returning nothing rather
than padding a thin item. `/health` reports `repeats_from_previous_days`.

## The local news section

`westwindsor` is the strictest section on the site. Small-town feeds are mostly
police blotter, courts, zoning and budgets, so a blocklist alone is not enough —
plenty of unsuitable local news trips no keyword at all ("Man, 34, charged
following incident on Route 571").

Local items therefore have to pass a **second, positive gate**
(`safety.is_local_safe`): as well as clearing the blocklist, the text must match
`safety.LOCAL_TOPICS` — schools, students, library, parks, festivals, youth
sport, volunteering, awards. Anything that doesn't look positively like
community news is dropped.

**An empty local section is the expected outcome most days**, and the page says
so in plain language rather than looking broken. That is the design. If you'd
rather see more there, widen `LOCAL_TOPICS` — do not weaken the blocklist.

## Summer Check-In

The first card on the page asks two things only: how they're feeling (five
mood buttons) and one thing they're grateful for today. Deliberately short —
a longer form is a form they stop filling in.

Entries are **write-only to the server**, exactly like feedback — they appear in
your dashboard and never on the public page. Separately, each entry is kept in
that browser's `localStorage`, so the kid sees their own summer list growing
underneath the form. That needs no server round trip and can't leak between
visitors.

## Sudoku and streaks

**Sudoku is not generated by the model.** A puzzle is only a puzzle if the
solution is unique, and that has to be proved rather than hoped for. `sudoku.py`
builds a complete grid, removes clues symmetrically, and after every removal
counts solutions — keeping the clue only if exactly one solution remains.
`builder.py` re-validates before the puzzle reaches the page. No API cost, no
failure mode, no network.

Sizes follow the existing age toggle: 6x6 (2x3 boxes) for age 9, 9x9 for age 11.
Conflicts are highlighted live rather than at the end — for a 9-year-old,
discovering at the finish that move six was wrong is just demoralising.

**Streaks** are tracked per game (Guess the Word, Make Four Groups, Sudoku) in
`localStorage`, keyed to the *content* date so they follow the 8pm rollover
rather than the wall clock. Solving twice in a day doesn't double-count, a
missed day resets the current streak, and the best-ever figure survives. Best
streaks are reported to the stats dashboard.

Caveat worth knowing: streaks are **per browser, not per child**. Sharing a
laptop means sharing a streak — the age toggle sets puzzle difficulty, not
identity. Separate devices give separate streaks.

## Feedback

The page ends with a rating (😍 / 🙂 / 😴), an optional favourite-section
picker, and a free-text box. Submissions are **write-only**: they go to the
parent dashboard and are never rendered back onto the public page.

Limits: 1,000 characters per note, 500 notes per day, and anything failing the
safety filter is surfaced with a `flagged` badge rather than dropped, since a
public endpoint means a stranger could post. The dashboard renders notes with
`textContent`.

## Engagement tracking

`/stats?token=<ADMIN_TOKEN>` shows how long each section is actually looked at,
which puzzles get opened, game results, and click-throughs — for today and
across all tracked days. Bars split by which age level was selected, a rough
proxy for which kid.

It records no names, accounts, IP addresses, cookies, typed text or guesses.
The session id is random and dies with the tab. `ANALYTICS=off` disables it.

Render's free plan has no persistent disk, so set `HF_TOKEN` +
`STATS_DATASET_REPO` or the history resets nightly. The dashboard warns you if
that's missing.

## Checking on it

`GET /health` reports which feeds worked, whether Claude ran, and which
sections fell back to the offline bank.

## Safety

Five layers, because any single one will eventually miss something.

1. **Blocklist on input.** `safety.py` screens every raw headline before it
   reaches the model. ~1,700 word forms plus 86 phrases, generated from stems
   so inflections are covered (`shooting` *and* `shootings`). A sports
   exception list keeps ordinary match language — "sudden death", "blowout",
   "crushed the" — from nuking the sports section.
2. **Blocklist on output.** Everything Claude returns is screened again:
   news, jokes, word of the day, puzzles, on-this-day, the Connections
   category names, and every game tile. Nothing reaches the page unscreened.
3. **Editorial instructions.** Claude is told to drop anything unsuitable for
   a 9-year-old and to return fewer items rather than soften a bad story.
4. **Link screening.** Outbound links are the only way off our page, so a link
   survives only if its domain is on the allowlist in `safety.py` and the URL
   is plain `https`. `javascript:` and `data:` URLs are impossible by
   construction, on the server and again in the browser. A story whose link
   fails still appears — it just isn't clickable.
5. **Structural validation.** A malformed puzzle can't render, so a broken
   grid can't confuse anyone.

There are two strictness tiers. Untrusted feed and model output gets the blunt
one, which drops even gentle mentions of death because the framing can't be
seen. Hand-written text in `fallback.py` gets a lighter explicit-content check,
so a story about an elderly regular passing away and his friends keeping his
table free is allowed through. That distinction is deliberate.

### What this does not do

- **It cannot vet the far side of a link.** The allowlist means the kids land
  on the BBC or ESPN rather than anywhere, but those pages have their own
  sidebars and related-story rails. For real off-site control, pair this with
  browser or router-level parental controls.
- **A keyword filter has no understanding.** It will miss an upsetting story
  written in gentle language. Claude is the layer meant to catch that, and
  Claude is not perfect either.
- **`/health` shows `blocked_by_filter`** — how much each filter dropped
  today. If that number is 0 every day, be suspicious rather than reassured.

Skim the page yourself for the first week or two.
