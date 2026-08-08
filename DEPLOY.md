# Deploying Kids Daily

**Host: Render (free plan). Planned run: ~30 days, to the end of summer.**
About 15 minutes to set up.

> **Why not HuggingFace?** Spaces that run compute — both Docker *and* Gradio —
> now require a paid HF plan. Only Static Spaces are free, and a static Space
> can't fetch RSS feeds or hold an API key. Render still has a real free tier
> for Python web services, so that's what this guide uses. The `Dockerfile`
> stays in the repo in case you ever move to a paid host; nothing else changes.
>
> Fly.io, Koyeb and Railway were considered and ruled out — Fly removed its
> free tier, Koyeb dropped free compute, Railway is trial-credit only.

You need: a GitHub account, a Render account (both free), and an Anthropic API key.

Total expected cost for the month: **under $2**, all of it Anthropic API usage.

---

## 1. Put the code on GitHub

Render deploys from a Git repo.

```bash
cd path/to/kids-daily

git init
git add .
git commit -m "Kids Daily"
git branch -M main
git remote add origin https://github.com/<your-username>/kids-daily.git
git push -u origin main
```

The repo can be private — Render connects either way.

## 2. Create the Render service

1. <https://dashboard.render.com> → **New** → **Web Service**
2. Connect GitHub, pick the `kids-daily` repo
3. Render reads `render.yaml` and fills everything in. Confirm:

   | Field | Value |
   |---|---|
   | Runtime | Python 3 |
   | Build command | `pip install -r requirements.txt` |
   | Start command | `uvicorn app:app --host 0.0.0.0 --port $PORT` |
   | Instance type | **Free** |

4. **Create Web Service**

**Don't change the start command.** Render assigns the port through `$PORT`;
binding a fixed port makes the health check fail and the deploy hang.

First build takes 3–5 minutes. Your URL will be
`https://kids-daily-XXXX.onrender.com`.

## 3. Add your API key

**Dashboard → your service → Environment → Add Environment Variable**

| Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | your key from <https://console.anthropic.com/settings/keys> |
| `ADMIN_TOKEN` | any random string (lets you force a rebuild) |

Saving triggers a redeploy.

While you're in the Anthropic console, **set a monthly spend cap** — $5 is
plenty. If it's ever hit, the site falls back to its offline bank rather than
breaking.

## 4. Check it worked

Visit `https://<your-service>.onrender.com/health`:

```json
{
  "status": "ok",
  "api_key_present": true,
  "links_mode": "allowlist",
  "sections_using_offline_bank": [],
  "blocked_by_filter": { "feed_kids_news": 2, "feed_eagles": 1 },
  "sources": { "kids_news": "rss ok (8 items) ...", ... }
}
```

- `"api_key_present": false` → the variable didn't save. Re-add it.
- `"status": "degraded"` with entries in `sections_using_offline_bank` → check
  `sources` and `llm`, which say exactly what failed.
- `blocked_by_filter` counts what the safety filter dropped today. Small
  non-zero numbers mean it's working. If it's `{}` every day, be suspicious
  rather than reassured.
- `freshness_relaxed` names any section where nothing new was available and the
  no-repeats rule had to be relaxed to avoid rendering a blank card. Seeing
  `cricket` in there during an off-week is normal.

Then open the site and play both games through once.

## 5. Worth doing: stop the morning cold start

Free services sleep after 15 minutes of no traffic and take ~1 minute to wake,
plus 20–40 seconds to build the day. If the kids open it at 7am cold, that's a
long wait in front of a blank page.

Fix: ping it on a schedule with a free cron service —
<https://cron-job.org> or <https://uptimerobot.com>.

- **URL:** `https://<your-service>.onrender.com/ping`
- **Schedule:** every 10 minutes, **5:45am–9:00pm** your time

That first ping builds the day before anyone looks at it.

**Point the cron at `/ping`, not `/health`.** cron-job.org reads at most
**64 KB** of a response and aborts the job with *"output too large"* if you go
over — so a monitoring endpoint should say as little as possible. `/ping`
returns 14 bytes (`ok 2026-08-08`), answers instantly, and still kicks off the
day's build on a background thread. `/health` is for you to read, not for a
robot: it carries the whole diagnostics block.

If you want the cron to actually check health rather than just poke the
service, use `/health?brief=1` — 138 bytes, with `status` and `date` in it.
cron-job.org can then match on the response containing `"status": "ok"`.

The free plan allows 750 instance hours per month; a ~15-hour daily window is
around 465, so there's plenty of margin. (Pinging 24/7 would burn ~744 and any
redeploy could tip you into suspension — don't.)

## 5b. When the page changes over

`DAY_ROLLOVER_HOUR` controls the moment the next day's page goes live.

| Value | Effect |
|---|---|
| `20` | **current setting** — new page appears at 8pm local time |
| `0` or unset | normal midnight rollover |

At 8pm the kids get an entirely fresh page: new puzzles, Wordle, joke, news,
and the header date reads tomorrow. It then stays put until 8pm the next
evening, so nothing shifts under them mid-morning.

You don't need a separate cron job for this — the 10-minute keep-alive ping
hits `/ping` at 8:00pm, which starts the build automatically. `/ping` replies
before the build finishes, so the job is never sitting there waiting on Claude
and eight RSS feeds; the page is ready a minute or so later.

`SITE_TZ` is `America/New_York`, so this tracks the local clock through the
EDT/EST switch. It's 8pm all year, not 8pm EST drifting to 7pm.

`/health` reports `day_rollover_hour` and `server_time` so you can confirm it.

**Cost note:** without the storage in step 6, the overnight sleep wipes the
cache, so the page gets built at 8pm *and* again on the morning's first ping —
roughly 4¢/day instead of 2¢. Trivial either way, but it's one more reason to
do step 6.

---

## 6. Storage — now required, because of stats

**I told you to skip this earlier. Adding tracking changes that.**

Render's free plan has no persistent disk, and the service wipes its filesystem
every time it sleeps. Without storage you lose the engagement history every
night, so the "all time" view can never show more than the current day.

Free HuggingFace *datasets* are still free — it's only Spaces compute that
isn't. So your HF account still earns its keep:

1. Create a **private dataset** at <https://huggingface.co/new-dataset>, e.g.
   `<your-hf-username>/kids-daily-data`
2. Make a **write** token at <https://huggingface.co/settings/tokens>
3. In Render → Environment, add:

   | Name | Value |
   |---|---|
   | `HF_TOKEN` | the write token |
   | `STATS_DATASET_REPO` | `<your-hf-username>/kids-daily-data` |
   | `CACHE_DATASET_REPO` | `<your-hf-username>/kids-daily-data` |

The same dataset holds both: the generated day (so it isn't rebuilt and
re-billed after every restart) and the engagement log. Stats are pushed at most
once every 5 minutes and on shutdown, then pulled back on boot.

The stats dashboard shows a warning banner if this isn't configured, so you'll
know immediately.

---

## 7. Your stats dashboard

Open:

```
https://<your-service>.onrender.com/stats?token=<ADMIN_TOKEN>
```

Bookmark that. It has two tabs:

- **Today** — time on page, visits, which sections got the attention, Wordle
  and Groups results, how often answers were peeked at.
- **All time** — the same totals across every tracked day, plus a day-by-day
  bar chart and table showing what each day's most-used section was.

The bars split by **which age level was selected** (blue = 9, purple = 11),
which is a rough proxy for which kid was looking. It's a proxy, not an
identity — if they share a laptop without touching the toggle, the time lands
under whoever was last selected.

### What is and isn't recorded

Recorded: how long each section was on screen with the tab focused, which
puzzles were opened, game results, link click-throughs, age-toggle switches.

**Not** recorded: no names, no accounts, no IP addresses, no cookies, nothing
they type, and not their actual guesses. The session id is random and dies with
the tab.

To turn tracking off entirely, set `ANALYTICS=off` in Render → Environment.

### Feedback from the kids

The page ends with a **Tell Me What You Think** card: a 😍 / 🙂 / 😴 rating, an
optional "favourite bit today", and a free-text box. Notes appear in the
dashboard under **What they said**, newest first, tagged with the age level
that was selected.

It is deliberately **write-only**. Nothing anyone submits is ever displayed
back on the public page — otherwise a public children's site would have an open
comment board on it. Only you see the notes.

Because the endpoint is public, a stranger who finds the URL could post
something. Three things limit the damage: messages are capped at 1,000
characters, the day's file is capped at 500 entries, and anything tripping the
safety filter is shown to you with a red **flagged** badge rather than hidden —
you should see it, just forewarned. Notes are rendered with `textContent`, so a
pasted `<script>` tag is text, not code.

### A suggestion

Tell them the site counts which parts get used. Framed as "I want to know which
bits to keep" it's just honest, they'll probably find it interesting, and it
avoids the situation where an 11-year-old discovers `/stats` on his own and
concludes he was being watched. He is old enough to find it.

---

## 8. Outbound links

Links are **on**, restricted to an allowlist. A "Read the full story" button
appears only when the article lives on a vetted domain — headed by **BBC,
ESPN, ESPNcricinfo and Bleeding Green Nation**, plus other reputable outlets in
`safety.ALLOWED_LINK_DOMAINS`.

Two things to expect:

- **Some stories will have no link.** Google News is the coverage fallback for
  each topic, and its links redirect through `news.google.com` to a publisher
  nobody has vetted, so they're stripped. The story still appears with its
  summary. That's the design, not a failure.
- **Bleeding Green Nation is a fan blog**, not a newsroom. Its headlines pass
  the same safety filter as everything else, but its article pages carry
  comment threads that no filter here can see and that aren't moderated to a
  9-year-old's standard.

To change it, set `LINKS_MODE` in Render → Environment:

| Value | Effect |
|---|---|
| `allowlist` | default — vetted domains only |
| `off` | no outbound links at all; summaries only |
| `all` | any `https` link (still blocks `javascript:` / `data:`) |

To narrow it to exactly the four sites you named, edit
`safety.ALLOWED_LINK_DOMAINS` — there's a one-line replacement in a comment
directly beneath it.

An allowlisted domain gets them to a reputable *site*, not a vetted *page*.
Browser or router-level parental controls remain the real protection for
off-site browsing; this setting is not a substitute.

---

## What it costs for 30 days

| | per day | 30 days |
|---|---|---|
| Claude, feeds working | ~$0.02 | ~$0.60 |
| Claude, feeds down (web search kicks in) | ~$0.08 | ~$2.40 |
| Render free plan | — | $0 |

Budget **under $2** in practice.

---

## Turning the difficulty up or down

All of it is one number or one line, and none of it needs a rebuild of the
content — only a redeploy.

| What | Where | Now | To make it easier |
|---|---|---|---|
| 6×6 Sudoku | `sudoku.py` → `SPECS[6]["givens"]` | `12` | raise it — `15` is where it was |
| 9×9 Sudoku | `sudoku.py` → `SPECS[9]["givens"]` | `44` | raise it; below ~36 it gets long |
| Wordle clue lock | `static/app.js` → `WL_CLUE_AFTER` | `3` guesses | set to `0` for the clue straight away |
| Word choice | `llm.py` → the `wordle.easy` / `wordle.hard` rules | tricky shapes | soften the wording |
| Groups board | `llm.py` → the `connections` rules | wordplay + traps | drop the "at most ONE plain category" line |

Two things the Sudoku numbers won't do:

- **Below about 12 clues a 6×6 stops working.** There isn't a unique
  no-guessing puzzle down there, so the generator quietly keeps more clues
  instead. 12 is the floor, not a preference — measured, not guessed.
- **Clue count is not difficulty.** Every puzzle shipped is solvable with
  nothing but naked and hidden singles, proven at build time. Fewer clues means
  more scanning, never a dead end where she has to guess.

Which is why the Sudoku card now has its own **6×6 / 9×9** buttons. If the 6×6
is still too quick, that's the ladder — and it's her choice, saved on her
device, independent of the page's age toggle.

## Everyday operations

**Force a rebuild** (a bad joke slipped through):

```bash
# 1. wake the service first, so the rebuild isn't racing a cold start
curl -s -w " <- awake\n" "https://<your-service>.onrender.com/ping"

# 2. kick off the rebuild - returns straight away with 202
curl -sS -X POST -w "\nHTTP %%{http_code}\n" \
  "https://<your-service>.onrender.com/api/refresh?token=<ADMIN_TOKEN>"

# 3. watch it finish (generated_at will change, usually 20-40s later)
curl -s "https://<your-service>.onrender.com/api/refresh/status?token=<ADMIN_TOKEN>"
```

**If curl prints a wall of HTML**, it is not coming from this app — every error
this app produces is JSON. It is Render's edge proxy, and it means one of:

- the service was **asleep** and the request hit the wake-up page. Run the
  `/health` call first and retry.
- a **deploy was in progress**. Wait for it to go green in the dashboard.
- the request **outran Render's proxy timeout**. This used to happen because
  `/api/refresh` rebuilt everything before replying; it now returns 202
  immediately and rebuilds in the background, so it should not recur. If you
  want the old blocking behaviour, add `&wait=true` — and expect HTML if it
  runs long.

To see what you actually got rather than a screenful of markup:

```bash
curl -s -o /dev/null -w "%%{http_code} %%{content_type}\n" -X POST \
  "https://<your-service>.onrender.com/api/refresh?token=<ADMIN_TOKEN>"
```

`202 application/json` is success. Anything with `text/html` is Render, not us.

**If the cron job fails with "output too large"**, cron-job.org stopped reading
because the response went past its **64 KB** ceiling. Point the job at `/ping`.
If it still fails, the job is not on the URL you think it is — check what size
each one actually returns:

```bash
for p in /ping "/health?brief=1" /health /api/today / ; do
  printf "%-18s " "$p"
  curl -s -o /dev/null -w "%%{size_download} bytes  %%{content_type}\n" \
    "https://<your-service>.onrender.com$p"
done
```

Measured on the live site, for reference:

| Endpoint | Size | Safe for a cron? |
|---|---|---|
| `/ping` | 14 B | yes — use this |
| `/health?brief=1` | 138 B | yes |
| `/health` | ~2.5 KB | yes, but it's meant for you |
| `/` | 11 KB | fine |
| `/api/today` | ~15 KB | fine |
| `/api/stats.json` | grows with use | **no** — it carries every note the kids have written |
| `/static/hero.jpg` | 517 KB | **no** — the only thing here over 64 KB by itself |

**Deploy a change.** Push to `main`; Render rebuilds automatically.

**Change what the kids get.** Everything editorial lives in the two prompts in
`llm.py` — `HOUSE_RULES` (tone and safety) and the JSON blocks in
`generate_creative` / `edit_news`. Want harder math, a third sports topic, a
science-fact section? Edit the prompt, add the field to the frontend, push.

**Add or change topics.** `sources.FEEDS` is a plain dict of feed URLs, tried
in order. Add a key there, a matching section in `llm.edit_news`, and render it
in `static/app.js`.

**Tune the safety list.** In `safety.py`: `STEMS` holds words that get
inflected automatically (add `shoot`, get `shootings` free), `PHRASES` holds
literal multi-word matches, `SPORTS_SAFE` keeps ordinary match language
("sudden death", "blowout") from nuking the sports section, and
`ALLOWED_LINK_DOMAINS` controls which sites may be linked.

**Swap the hero photo.** Replace `static/hero.jpg` and regenerate the blurred
backdrop — instructions at the top of `static/style.css`. Re-check the title
contrast afterwards.

---

## Shutting it down at the end of summer

Two minutes, and worth actually doing so nothing keeps running or billing:

1. **Render** → service → Settings → **Delete Web Service**
2. **Anthropic console** → revoke the API key you made for this
3. **Download the stats first** if you want to keep them —
   `https://<your-service>.onrender.com/api/stats.json?token=<ADMIN_TOKEN>`
   saves the whole history as JSON. The HF dataset keeps a copy either way
4. **cron-job.org / UptimeRobot** → delete the ping job (otherwise it hammers a
   dead URL forever)
5. The GitHub repo can stay — it costs nothing and makes next summer a
   five-minute redeploy

## Known limits

- **The offline bank repeats.** 7 math puzzles, 7 logic puzzles, 18 jokes,
  6 stories, 14 words, 50 Wordle words, 6 Connections grids. It's a safety net
  for a bad API day, not a way to run without a key. Over a 30-day run with the
  API working you'll never see it; if the key fails you'll notice repeats
  inside a week.
- **Free-tier cold starts** — ~1 minute after 15 minutes idle, unless you set
  up step 5.
- **Feed URLs are unverified.** I had no network access when building this, so
  every RSS endpoint — including Bleeding Green Nation's — is untested in
  practice. Each topic has backups and Claude's web search behind it. Check
  `/health` on day one to see which sources actually worked.
- **The safety filter is keyword-based.** It has no comprehension, so an
  upsetting story told in gentle language can pass it. Claude is the layer
  meant to catch that, and Claude isn't perfect either. Skim the page yourself
  for the first few days.
- **Links are on for vetted domains.** The filter screens the headline, not the
  page behind it, and not its comment section. `LINKS_MODE=off` closes that
  door entirely.
