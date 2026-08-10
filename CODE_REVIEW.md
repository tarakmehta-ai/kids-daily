# Kids Daily — Code Review

Reviewed 8 August 2026, against the tree as deployed at `ksisters.onrender.com`.
~7,000 lines across 8 Python modules and a 3-file frontend.

I wrote most of this code, so treat the praise with the appropriate suspicion and
the criticism as the useful part. Every finding below was reproduced against the
actual source before being written down; where I could demonstrate a bug, the
demonstration is included.

---

## Verdict

The system does what it was built to do and it fails in the right direction —
when something breaks, a child sees slightly duller content rather than a broken
page or an unsuitable headline. The safety design is layered rather than
trusting any single check, the Sudoku generator makes a guarantee it can
actually prove, and the diagnostics are honest enough that most of this session's
bugs were found by reading `/health` rather than by a kid complaining.

Two things genuinely worry me:

1. **A real hole in the safety filter** (H1). Hyphenated phrases in the
   blocklist can never match. `Hit-and-run driver sought on Route 571` passes;
   the same headline without hyphens is blocked.
2. **There are no tests in the repository.** None. Everything in this project
   was verified in a throwaway sandbox that no longer exists.

Everything else is tuning, tidying, or things that only matter if this outlives
the summer.

---

## What is actually good

Worth stating plainly, because the rest of this document is a list of problems.

- **Safety is layered, not stacked on one check.** Blocklist before the model,
  editorial instructions inside the model, blocklist again after, structural
  validation, then a URL allowlist. Any single layer failing still leaves four.
- **The Sudoku guarantee is real.** `sudoku.py` only keeps a clue removal if the
  puzzle remains *both* uniquely solvable and solvable by naked/hidden singles
  alone. The no-guessing promise is true by construction, not by hope. That is
  the most quietly correct code in the project.
- **`_salvage_json` earns its keep.** Recovering the largest valid prefix of a
  truncated model response has saved a full day's news at least once.
- **Diagnostics are specific.** `blocked_by_filter`, `freshness_relaxed`,
  `creative_swapped_to_avoid_repeat`, `fell_back_to_bank` and now `notes` each
  answer a different question. Compare with a single `status: degraded`, which
  would have told you nothing useful all week.
- **Dependencies are pinned exactly** and `.gitignore` correctly excludes the
  798 KB `preview.html`.
- **Comments explain *why*, including past mistakes.** `safety.py` documents the
  inflection bug that let 18 of 20 bad headlines through. That comment is worth
  more than the code around it.

---

## HIGH

### H1 — Hyphenated blocklist phrases can never match

`safety.py`, `_normalise()` vs `PHRASES` / `SPORTS_SAFE`

`_normalise()` deletes hyphens from the text before matching:

```python
t = re.sub(r"[\*\-_\.•]+", "", t)      # so "f.u.c.k" and "k-i-l-l" are caught
```

but the blocklist patterns are matched **as written**. Any pattern containing a
hyphen is therefore unreachable — the text no longer contains a hyphen by the
time the regex runs.

Reproduced:

```
SAFE   Hit-and-run driver sought on Route 571
BLOCK  Hit and run driver sought on Route 571
SAFE   Victim in life-threatening condition after crash
BLOCK  Victim in life threatening condition after crash
SAFE   Police investigate drive-by incident
```

Same story, opposite outcome, decided by a punctuation mark the source
publication chose.

Dead patterns: **6 of 137** in `PHRASES` (`self-harm`, `self-harming`,
`drive-by`, `hit-and-run`, `life-threatening`, `stand-off`), **3 of 62** in
`SPORTS_SAFE` (`shoot-out`, `half-volley`, `sudden-death`), **1** in
`LOCAL_TOPICS` (`clean-up`).

Mitigating: `self-harm` normalises to `selfharm`, which *is* in `STEMS`, so that
one is covered by a different layer. `stand-off` → `standoff`, also listed
separately. The genuinely exposed cases are `hit-and-run`, `life-threatening`
and `drive-by` — and local news is exactly where hyphenated police-blotter
phrasing shows up.

The `SPORTS_SAFE` misses fail in the safe direction: `sudden-death` not being
blanked means a legitimate sports headline gets dropped, which is annoying, not
dangerous.

**Fix.** Normalise the patterns with the same function that normalises the text,
and keep both forms:

```python
_PHRASE_FORMS = {p for p in PHRASES} | {_normalise(p) for p in PHRASES}
```

Same for `SPORTS_SAFE` and `LOCAL_TOPICS`. Add a regression test asserting that
for every entry in these lists, the phrase is blocked in hyphenated, spaced and
run-together form.

---

### H2 — No tests exist in the repository

Everything in this project was validated by scripts written into `/tmp` in a
sandbox, run once, and discarded. That includes:

- the safety corpus (45 realistic bad headlines, all blocked, zero false
  positives on good ones)
- the Sudoku uniqueness and singles-solvability proofs across 30 days
- the Wordle keyboard-capture fix
- the 30-day adversarial de-duplication simulation
- 34 independently recomputed arithmetic answers in the maths bank

None of it can be re-run. Every one of those results is now a claim in a chat
log rather than a check that would fail if someone broke it. Given that this
code is filtering news for a 9-year-old, that is the wrong place for the safety
corpus to live.

**Fix.** A `tests/` directory and `pytest` in `requirements-dev.txt`. In
priority order:

| Test | Why it matters |
|---|---|
| `test_safety.py` — the bad-headline corpus, both hyphenated and not | The one thing that must not silently regress |
| `test_safety.py` — good headlines that must NOT be blocked | False positives are how you end up with blank sections |
| `test_sudoku.py` — 30 days × 2 sizes, unique + singles-only | Guarantees the promise on the page |
| `test_dedupe.py` — the 30-day stuck-model simulation | The bug the girls actually noticed |
| `test_banks.py` — every bank entry validates, no duplicate keys, no leaked answers in hints | Cheap, catches copy-paste errors |
| `test_builder.py` — a partial model response must not silently become "claude ok" | Today's five-section fallback |

The Anthropic and httpx stubs used during development are ~30 lines each and
belong in `tests/conftest.py`. That alone would make the suite runnable offline
in CI.

---

## MEDIUM

### M1 — The admin token travels in the URL

`app.py` — `/stats?token=`, `/api/refresh?token=`, `/api/stats.json?token=`

Query strings end up in places you do not control: Render's HTTP access logs,
browser history, and the `Referer` header of any outbound request made from the
stats page. The token guards a rebuild trigger and a page containing everything
the children have written.

`_require_admin` itself is correct — it uses `secrets.compare_digest`, so no
timing leak. The problem is transport, not comparison.

**Fix.** Accept `X-Admin-Token` as a header and prefer it; keep the query
parameter for bookmark and cron convenience if you want, but know that it is
logged. At minimum, rotate `ADMIN_TOKEN` when the site is retired — it has been
pasted into this chat, a cron service, and your shell history.

### M2 — Two analytics event types are silently discarded

`analytics.py` `EVENT_TYPES` vs `static/app.js`

```
emitted by frontend : age_switch, conn_result, joke_reveal, link_click, reveal,
                      session, sudoku_level, sudoku_result, view, wordle_clue,
                      wordle_result
accepted by analytics: (the same list, minus sudoku_level and wordle_clue)
SILENTLY DROPPED    : sudoku_level, wordle_clue
```

`_clean_event()` returns `None` for an unrecognised type and the event vanishes
without a log line. Both dropped types were added by me this week, and both are
exactly the data needed to answer the questions that prompted them: *is the
three-guess clue gate too strict?* and *did she ever actually tap the 9×9?*

The whitelist itself is the right design — it stops a stray POST bloating the
log. It just needs to be updated in the same commit as the frontend.

**Fix.** Add both to `EVENT_TYPES`. Then add a test that parses `app.js` for
`type: "..."` literals and asserts every one is accepted — the check I ran to
find this is three lines and should not have been a one-off.

### M3 — The Summer Check-In is invisible in the stats

`s-summer` exists in `index.html` and the nav, but is absent from
`analytics.SECTIONS` and `SECTION_LABELS`. Time spent there is recorded but
bucketed as `"other"`, so the section you deliberately put at the top of the
page is the one section the dashboard cannot name.

**Fix.** One line in each set.

### M4 — `/api/stats.json` grows without bound

`app.py` returns `analytics.overall()` plus `read_feedback()` (60 days) plus
`read_journal()` (90 days), in full, every call. Aggregates are bounded;
the message lists are not. This is the one endpoint that will eventually cross
the 64 KB ceiling that already broke the cron job once.

**Fix.** Paginate, or cap the returned messages and add a `?since=` parameter.
For a 30-day run it will not bite — but it is the reason to not point any
monitor at it.

### M5 — The write endpoints are unauthenticated

`/api/track`, `/api/feedback` and `/api/journal` accept anonymous POSTs. This is
intentional — the page has no login and children should not have one — and the
damage is capped: 200 events per request, `MAX_PER_DAY = 500` messages, hard
clamps on every numeric field, and a type whitelist.

But `/api/feedback` is a text field that renders on your dashboard. Anyone who
learns the URL can put arbitrary text in front of you. The `flagged` marking
helps; obscurity is doing the rest of the work.

For a two-child site living 30 days, that is a defensible trade. It would not be
if this ran longer or were shared. Worth a rate limit keyed on IP if it ever is.

---

## LOW

**L1 — `_wordkey` truncates at 220 characters.** Two long word problems sharing
vocabulary could produce the same key and trigger a needless swap. Harmless, but
it is the explanation if you ever see a puzzle swapped for no visible reason.

**L2 — The Wordle "fact" disappears when the bank rescues the word.** Bank
entries are `(word, hint)` pairs with no fact, so `_dedupe_creative` writes
`fact: ""` and the post-solve reward silently vanishes. Adding a third element
to the bank tuples would fix it; so would falling back to the hint.

**L3 — 33 blanket `except Exception` handlers.** Deliberate, and the right call
for a page that must never break in front of a child. The cost is that a genuine
bug shows up as `status: degraded` rather than a stack trace. Mostly mitigated
by the `SOURCE_LOG` / `LLM_LOG` notes, but it is why today's truncation went
unnoticed for a week.

**L4 — `xml.etree.ElementTree` on untrusted XML.** `parse_rss` catches only
`ET.ParseError`. ElementTree does not resolve external entities, but is
susceptible to entity-expansion blowups. The feeds are BBC, Google News and
ESPN, so this is theoretical — `defusedxml` is a one-line swap if you care.

**L5 — `renderConnections()` binds its click handlers on every call.** It is
called exactly once today, so there is no bug. But `setAge()` already re-invokes
its three siblings, and the day someone adds `renderConnections()` to that list,
every submit counts as two mistakes. The Wordle keyboard had precisely this bug
and it took a child to spot it. Use `{ once: true }` or a bound flag.

**L6 — `_pick_unused` and `_pick_unused_pair` are near-duplicates** differing
only in how they key an entry. One function taking a key-set function would do.

**L7 — The `word_of_day` swap does not update `seen["words"]`,** unlike the joke
and Wordle swaps which do. No live impact, because `seen` is not consulted again
in that pass. It is an inconsistency waiting to become a bug.

---

## Housekeeping

- **`Dockerfile` is vestigial.** Render uses the native Python runtime via
  `render.yaml`. The Dockerfile is a leftover from the abandoned HuggingFace
  Spaces plan. Keep it only if you might move hosts; otherwise it is a second
  build definition that will drift out of sync with the first.
- **`hero.jpg` is 517 KB** and served at full size to phones, with no `width`/
  `height` attributes, so it contributes layout shift on load. A ~60 KB WebP
  with a `srcset` would be a visible improvement on a phone over cellular.
- **`static/app.js` is one 1,160-line IIFE.** Fine at this size and genuinely
  simpler than a build step. Past ~1,500 lines the games should become separate
  ES modules.
- **`fallback.py` is 531 lines of content in a code file.** It is now the
  largest content asset in the project. Moving the banks to JSON would let a
  non-programmer add jokes, and would let the tests validate them as data.

---

## Suggested order

1. **H1** — the safety hole. One function, plus the test that proves it.
2. **H2** — stand up `tests/`, starting with the safety corpus.
3. **M2 + M3** — three lines, and they restore the measurements you are about to
   want when the girls give more feedback.
4. **M1** — header-based admin token, or at least rotate at the end of summer.
5. Everything else only matters if this runs past September.

---

## One structural observation

The recurring failure mode this week was not bad code — it was **silent
degradation**. The safety filter dropping a history event, the creative response
being truncated, the analytics whitelist swallowing new event types, hyphenated
phrases never matching. In each case the system did something reasonable, said
nothing, and carried on.

That is the right instinct for a page a child opens at breakfast. But it means
the diagnostics are not a nice-to-have — they are the only way you find out.
Every silent fallback should leave a trace in `/health`, and the ones added this
week (`notes`, the `[incomplete: ...]` marker) are worth more than they look.

The remaining gap: nothing is watching `/health` for you. `status: degraded` sat
there for hours today until you happened to ask. A five-line addition to the
existing cron — alert if `problems > 0` — would close it.
