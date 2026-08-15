/* Kids Daily - front end */
(function () {
  "use strict";

  // Safari private mode throws on any localStorage access, so everything goes
  // through these. Losing saved progress is fine; a blank page is not.
  function lsGet(k) {
    try { return window.localStorage.getItem(k); } catch (e) { return null; }
  }
  function lsSet(k, v) {
    try { window.localStorage.setItem(k, v); } catch (e) {}
  }

  var DATA = null;
  var AGE = lsGet("kd-age") || "9";

  // ---------- engagement tracking ----------
  // Records how long each section is on screen and which features get used.
  // No names, no accounts, no IPs, no text they type. The session id is random
  // and lives only until the tab closes. Everything here is wrapped so that a
  // tracking failure can never stop the page rendering.
  var TRACK = (function () {
    var queue = [];
    var sid = Math.random().toString(36).slice(2) + Date.now().toString(36);
    var start = Date.now();

    function push(ev) {
      try {
        ev.sid = sid;
        ev.age = AGE;
        queue.push(ev);
        if (queue.length >= 40) flush(false);
      } catch (e) {}
    }
    function flush(useBeacon) {
      if (!queue.length) return;
      var body = JSON.stringify({ events: queue });
      queue = [];
      try {
        if (useBeacon && navigator.sendBeacon) {
          navigator.sendBeacon("/api/track", new Blob([body], { type: "application/json" }));
        } else {
          fetch("/api/track", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: body,
            keepalive: true
          }).catch(function () {});
        }
      } catch (e) {}
    }
    function elapsed() { return (Date.now() - start) / 1000; }
    return { push: push, flush: flush, elapsed: elapsed };
  })();

  // ---------- streaks ----------
  // One streak per game, per browser. Stored against the CONTENT date, so it
  // follows the 8pm rollover rather than the wall clock. Sharing a laptop means
  // sharing a streak - the age toggle sets puzzle difficulty, not identity.
  var STREAK = (function () {
    function key(game) { return "kd-streak-" + game; }
    function read(game) {
      try {
        var v = JSON.parse(lsGet(key(game)));
        if (v && typeof v.streak === "number") return v;
      } catch (e) {}
      return { last: null, streak: 0, best: 0 };
    }
    function prevDay(iso) {
      var d = new Date(iso + "T12:00:00");   // midday avoids any DST edge
      d.setDate(d.getDate() - 1);
      return d.toISOString().slice(0, 10);
    }
    // Called on a win. Idempotent: solving twice in a day doesn't double-count.
    function win(game) {
      var st = read(game), today = DATA.date;
      if (st.last === today) return st;
      st.streak = (st.last === prevDay(today)) ? st.streak + 1 : 1;
      st.last = today;
      st.best = Math.max(st.best || 0, st.streak);
      lsSet(key(game), JSON.stringify(st));
      return st;
    }
    // A streak is only "live" if it was kept today or yesterday.
    function current(game) {
      var st = read(game);
      if (!st.last) return 0;
      if (st.last === DATA.date || st.last === prevDay(DATA.date)) return st.streak;
      return 0;
    }
    function best(game) { return read(game).best || 0; }
    return { win: win, current: current, best: best, read: read };
  })();

  function paintStreak(game, elId) {
    var box = $("#" + elId);
    if (!box) return;
    var cur = STREAK.current(game), bst = STREAK.best(game);
    box.innerHTML = "";
    if (!cur && !bst) {
      box.appendChild(el("span", "streak-none", "Solve it to start a streak"));
      return;
    }
    if (cur > 0) {
      var pill = el("span", "streak-pill");
      pill.appendChild(el("span", "flame", "🔥"));
      pill.appendChild(document.createTextNode(
        cur + (cur === 1 ? " day" : " days") + " in a row"));
      box.appendChild(pill);
    } else {
      box.appendChild(el("span", "streak-none", "Streak broken - start again today"));
    }
    if (bst > 0) box.appendChild(el("span", "streak-best", "best " + bst));
  }

  // ---------- helpers ----------
  function $(sel, root) { return (root || document).querySelector(sel); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }
  function dec(s) {
    if (!s) return "";
    if (!DATA || !DATA._encoded) return s;
    try { return decodeURIComponent(escape(atob(s))); } catch (e) { return s; }
  }
  function hostOf(url) {
    try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return ""; }
  }
  // The server already screens every link, but this is the last gate before a
  // URL becomes clickable for a child. Anything that isn't plain https is
  // dropped, which also rules out javascript: and data: entirely.
  function safeHref(url) {
    if (!url) return "";
    try {
      var u = new URL(url, window.location.href);
      return u.protocol === "https:" ? u.href : "";
    } catch (e) { return ""; }
  }
  function linkTo(url, label) {
    var href = safeHref(url);
    if (!href) return null;
    var a = el("a", "readmore", label);
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener noreferrer nofollow";
    a.referrerPolicy = "no-referrer";
    a.addEventListener("click", function () {
      TRACK.push({ type: "link_click", domain: hostOf(href) });
      TRACK.flush(true);
    });
    return a;
  }
  // Deterministic shuffle so both kids see the same board all day.
  function seededShuffle(arr, seedStr) {
    var seed = 0, i;
    for (i = 0; i < seedStr.length; i++) seed = (seed * 31 + seedStr.charCodeAt(i)) >>> 0;
    function rnd() { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; }
    var out = arr.slice();
    for (i = out.length - 1; i > 0; i--) {
      var j = Math.floor(rnd() * (i + 1));
      var t = out[i]; out[i] = out[j]; out[j] = t;
    }
    return out;
  }
  // True when the keystroke belongs to something the child is writing in -
  // a textarea, an input, a dropdown. Games must keep their hands off those.
  function typingInAField(node) {
    if (!node) return false;
    if (node.isContentEditable) return true;
    var tag = (node.tagName || "").toUpperCase();
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
  }

  // Is this element inside a given section? Used so each game can claim the
  // keyboard while it has focus, instead of every handler seeing every key.
  function inSection(node, id) {
    if (!node || !node.closest) return false;
    return !!node.closest("#" + id);
  }

  function store(key, val) {
    lsSet("kd-" + DATA.date + "-" + key, JSON.stringify(val));
  }
  function load(key) {
    try { return JSON.parse(lsGet("kd-" + DATA.date + "-" + key)); } catch (e) { return null; }
  }

  // ---------- news ----------
  function newsCard(item, withTalk) {
    var c = el("article", "card");
    c.appendChild(el("h3", null, item.headline));
    if (item.source || item.link) {
      c.appendChild(el("div", "meta", item.source || hostOf(item.link)));
    }
    c.appendChild(el("p", null, item.summary || ""));
    if (withTalk && item.talk_about_it) {
      var t = el("div", "talk");
      t.appendChild(el("b", null, "Talk about it"));
      t.appendChild(document.createTextNode(item.talk_about_it));
      c.appendChild(t);
    }
    var link = linkTo(item.link, "Read the full story →");
    if (link) c.appendChild(link);
    return c;
  }

  function renderNews() {
    var box = $("#news");
    box.innerHTML = "";
    var items = DATA.kids_news || [];
    if (!items.length) {
      box.appendChild(el("p", "empty", "No news made it through today's check. Try again later."));
      return;
    }
    items.forEach(function (i) { box.appendChild(newsCard(i, true)); });
  }

  function renderSports() {
    var tabs = document.querySelectorAll(".tab");
    function show(team) {
      Array.prototype.forEach.call(tabs, function (t) {
        t.setAttribute("aria-selected", String(t.dataset.team === team));
      });
      var box = $("#sports-body");
      box.innerHTML = "";
      var items = DATA[team] || [];
      if (!items.length) {
        box.appendChild(el("p", "empty", "Nothing new here today."));
        return;
      }
      items.forEach(function (i) { box.appendChild(newsCard(i, false)); });
    }
    Array.prototype.forEach.call(tabs, function (t) {
      t.addEventListener("click", function () { show(t.dataset.team); });
    });
    show("eagles");
  }

  // ---------- local news ----------
  function renderLocal() {
    var box = $("#local");
    box.innerHTML = "";
    var items = DATA.westwindsor || [];
    if (!items.length) {
      // Genuinely the normal case. Small-town feeds are mostly police blotter
      // and council business, none of which passes the filter.
      box.appendChild(el("p", "empty",
        "Nothing from around town today. Local news is mostly grown-up stuff, so this one is often quiet."));
      return;
    }
    items.forEach(function (i) { box.appendChild(newsCard(i, false)); });
  }

  // ---------- word of the day ----------
  function renderWord() {
    var w = DATA.word_of_day || {};
    var box = $("#wotd");
    box.innerHTML = "";
    box.appendChild(el("div", "word", w.word || ""));
    var line = el("div");
    if (w.pronunciation) line.appendChild(el("span", "pron", w.pronunciation + "  "));
    if (w.part_of_speech) line.appendChild(el("span", "pos", w.part_of_speech));
    box.appendChild(line);
    box.appendChild(el("p", "def", w.definition || ""));
    if (w.example) box.appendChild(el("p", "example", "“" + w.example + "”"));
    if (w.origin) box.appendChild(el("p", "why", w.origin));
  }

  // ---------- puzzles ----------
  function puzzleCard(node, title, emoji) {
    var c = el("article", "card");
    var h = el("h3");
    h.appendChild(el("span", "emoji", emoji + " "));
    h.appendChild(document.createTextNode(title));
    c.appendChild(h);
    c.appendChild(el("p", "q", node.question || ""));

    var btn = el("button", "reveal", "Show the answer");
    var ans = el("div", "answer");
    // The answer is decoded ON FIRST CLICK, not at render time. It used to be
    // written into the page immediately and merely hidden with display:none,
    // which threw away the point of encoding it in the first place - Inspect
    // Element showed it in plain text, and it would have appeared outright if
    // the stylesheet ever failed to load.
    var built = false;
    btn.addEventListener("click", function () {
      if (!built) {
        built = true;
        ans.appendChild(el("div", "a", "Answer: " + dec(node.answer)));
        if (node.solution) ans.appendChild(el("div", "s", dec(node.solution)));
      }
      ans.classList.toggle("show");
      if (ans.classList.contains("show")) {
        TRACK.push({ type: "reveal", section: "s-brain", puzzle: title });
      }
      btn.textContent = ans.classList.contains("show") ? "Hide the answer" : "Show the answer";
    });
    c.appendChild(btn);
    c.appendChild(ans);
    return c;
  }

  function renderPuzzles() {
    var level = AGE === "11" ? "hard" : "easy";
    var box = $("#puzzles");
    box.innerHTML = "";
    var m = (DATA.math_puzzle || {})[level];
    var l = (DATA.logic_puzzle || {})[level];
    if (m) box.appendChild(puzzleCard(m, "Math puzzle", "🔢"));
    if (l) box.appendChild(puzzleCard(l, "Logic puzzle", "🧩"));
  }

  // ---------- joke ----------
  function renderJoke() {
    var j = DATA.joke || {};
    var box = $("#joke");
    box.innerHTML = "";
    box.appendChild(el("div", "setup", j.setup || ""));
    var p = el("div", "punch");
    var b = el("button", "reveal", "Tell me!");
    b.addEventListener("click", function () {
      // Decoded here rather than at render time - see puzzleCard.
      p.textContent = dec(j.punchline);
      p.classList.add("show");
      b.style.display = "none";
      TRACK.push({ type: "joke_reveal", section: "s-joke" });
    });
    box.appendChild(b);
    box.appendChild(p);
  }

  // ---------- on this day ----------
  function renderHistory() {
    var box = $("#history");
    box.innerHTML = "";
    (DATA.on_this_day || []).forEach(function (e) {
      var c = el("article", "card");
      if (e.year) c.appendChild(el("div", "year", e.year));
      c.appendChild(el("h3", null, e.headline || ""));
      c.appendChild(el("p", null, e.blurb || ""));
      if (e.why_cool) c.appendChild(el("p", "why", e.why_cool));
      box.appendChild(c);
    });
  }

  // ---------- feel-good story ----------
  function renderStory() {
    var s = DATA.feelgood || {};
    var box = $("#story");
    box.innerHTML = "";
    if (!s.title) {
      box.appendChild(el("p", "empty", "No story today."));
      return;
    }
    var kind = s.kind || "true";
    var label = kind === "parable" ? "A story with a lesson"
      : kind === "retold" ? "Retold story"
      : "True story";
    var badge = el("span", "badge " + (kind === "parable" ? "parable" : "true"), label);
    box.appendChild(badge);
    box.appendChild(el("h3", null, s.title));
    if (s.source) box.appendChild(el("div", "meta", s.source));
    String(s.story || "").split(/\n\n+/).forEach(function (para) {
      if (para.trim()) box.appendChild(el("p", null, para.trim()));
    });
    if (s.lesson) box.appendChild(el("div", "lesson", s.lesson));
    var link = linkTo(s.link, "Read the original →");
    if (link) box.appendChild(link);
  }

  // ---------- wordle ----------
  var WL = { answer: "", guesses: [], current: "", done: false, clueShown: false };

  // The clue no longer sits there for the taking. Three real attempts first -
  // enough that the letters have told you something, so the clue confirms a
  // hunch instead of replacing one.
  var WL_CLUE_AFTER = 3;

  function wlPaintClue() {
    var btn = $("#wl-clue-btn");
    if (!btn) return;
    if (WL.clueShown || WL.done) { btn.style.display = "none"; return; }
    var left = WL_CLUE_AFTER - WL.guesses.length;
    btn.style.display = "";
    if (left > 0) {
      btn.disabled = true;
      btn.textContent = "Clue unlocks after " + left + (left === 1 ? " more try" : " more tries");
    } else {
      btn.disabled = false;
      btn.textContent = "Stuck? Get a clue";
    }
  }

  function wlScore(guess, answer) {
    // Two passes so repeated letters colour the way real Wordle does.
    var res = new Array(5).fill("absent");
    var pool = {};
    var i, ch;
    for (i = 0; i < 5; i++) {
      if (guess[i] === answer[i]) res[i] = "correct";
      else pool[answer[i]] = (pool[answer[i]] || 0) + 1;
    }
    for (i = 0; i < 5; i++) {
      if (res[i] === "correct") continue;
      ch = guess[i];
      if (pool[ch] > 0) { res[i] = "present"; pool[ch]--; }
    }
    return res;
  }

  function wlDrawBoard() {
    var board = $("#wl-board");
    board.innerHTML = "";
    for (var r = 0; r < 6; r++) {
      var row = el("div", "wordle-row");
      var guess = WL.guesses[r];
      var scored = guess ? wlScore(guess, WL.answer) : null;
      for (var c = 0; c < 5; c++) {
        var t = el("div", "wl-tile");
        if (guess) {
          t.textContent = guess[c];
          t.classList.add(scored[c]);
        } else if (r === WL.guesses.length && WL.current[c]) {
          t.textContent = WL.current[c];
          t.classList.add("filled");
        }
        row.appendChild(t);
      }
      board.appendChild(row);
    }
    wlPaintKeys();
  }

  function wlPaintKeys() {
    var best = {};
    var rank = { absent: 0, present: 1, correct: 2 };
    WL.guesses.forEach(function (g) {
      var s = wlScore(g, WL.answer);
      for (var i = 0; i < 5; i++) {
        var ch = g[i];
        if (best[ch] === undefined || rank[s[i]] > rank[best[ch]]) best[ch] = s[i];
      }
    });
    document.querySelectorAll("#wl-kb .key").forEach(function (k) {
      k.classList.remove("correct", "present", "absent");
      var v = best[k.dataset.key];
      if (v) k.classList.add(v);
    });
  }

  function wlToast(msg) { $("#wl-toast").textContent = msg || ""; }

  function wlSubmit() {
    if (WL.done) return;
    if (WL.current.length !== 5) { wlToast("Needs 5 letters!"); return; }
    WL.guesses.push(WL.current);
    var won = WL.current === WL.answer;
    WL.current = "";
    if (won) {
      WL.done = true;
      var st = STREAK.win("wordle");
      wlToast("You got it! 🎉");
      paintStreak("wordle", "wl-streak");
      wlFinish(true);
      TRACK.push({ type: "wordle_result", section: "s-wordle", won: true,
                   guesses: WL.guesses.length, streak: st.streak });
    } else if (WL.guesses.length >= 6) {
      WL.done = true;
      wlToast("The word was " + WL.answer);
      wlFinish(false);
      TRACK.push({ type: "wordle_result", section: "s-wordle", won: false, guesses: 6 });
    } else {
      wlToast("");
    }
    store("wordle-" + wlLevel(), { guesses: WL.guesses, done: WL.done });
    wlPaintClue();
    wlDrawBoard();
  }

  function wlKey(k) {
    if (WL.done) return;
    if (k === "ENTER") return wlSubmit();
    if (k === "BACK") { WL.current = WL.current.slice(0, -1); wlToast(""); return wlDrawBoard(); }
    if (/^[A-Z]$/.test(k) && WL.current.length < 5) {
      WL.current += k;
      wlDrawBoard();
    }
  }

  function wlBuildKeyboard() {
    var rows = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"];
    var kb = $("#wl-kb");
    kb.innerHTML = "";
    rows.forEach(function (r, idx) {
      var row = el("div", "kb-row");
      if (idx === 2) {
        var e = el("button", "key wide", "Enter");
        e.type = "button";
        e.dataset.key = "ENTER";
        row.appendChild(e);
      }
      r.split("").forEach(function (ch) {
        var b = el("button", "key", ch);
        b.type = "button";
        b.dataset.key = ch;
        row.appendChild(b);
      });
      if (idx === 2) {
        var d = el("button", "key wide", "Del");
        d.type = "button";
        d.dataset.key = "BACK";
        row.appendChild(d);
      }
      kb.appendChild(row);
    });
    kb.addEventListener("click", function (ev) {
      var b = ev.target.closest(".key");
      if (!b) return;
      // Without this the tapped key keeps focus, so the next Enter or Space
      // from the real keyboard fires that key a second time.
      b.blur();
      wlKey(b.dataset.key);
    });
  }

  function wlLevel() { return AGE === "11" ? "hard" : "easy"; }

  function wlShareGrid() {
    // The emoji grid people post from real Wordle. Pure fun, and it gives a
    // reason to come back and beat yesterday.
    var out = [];
    WL.guesses.forEach(function (g) {
      out.push(wlScore(g, WL.answer).map(function (s) {
        return s === "correct" ? "🟩" : s === "present" ? "🟨" : "⬜";
      }).join(""));
    });
    return "Kids Daily " + DATA.date + "  " + WL.guesses.length + "/6\n" + out.join("\n");
  }

  function wlFinish(won) {
    var box = $("#wl-after");
    box.innerHTML = "";
    var node = (DATA.wordle || {})[wlLevel()] || {};
    if (won && node.fact) box.appendChild(el("p", "wl-fact", node.fact));
    var grid = el("pre", "wl-share", wlShareGrid());
    box.appendChild(grid);
    var copy = el("button", "reveal", "Copy my score");
    copy.addEventListener("click", function () {
      try {
        navigator.clipboard.writeText(wlShareGrid());
        copy.textContent = "Copied!";
      } catch (e) { copy.textContent = "Select the squares above to copy"; }
    });
    box.appendChild(copy);
    box.classList.add("show");
  }

  function renderWordle() {
    var node = (DATA.wordle || {})[wlLevel()] || {};
    WL.answer = dec(node.word).toUpperCase();
    WL.guesses = []; WL.current = ""; WL.done = false;
    var saved = load("wordle-" + wlLevel());
    if (saved && Array.isArray(saved.guesses)) {
      WL.guesses = saved.guesses;
      WL.done = !!saved.done;
    }
    // The clue used to sit on screen permanently, which is most of why this
    // felt too easy. It is now behind a button, and the button is locked for
    // the first three guesses.
    WL.clueShown = false;
    var clue = $("#wl-hint"), btn = $("#wl-clue-btn");
    clue.textContent = "";
    clue.classList.remove("show");
    btn.onclick = function () {
      if (WL.guesses.length < WL_CLUE_AFTER) return;
      WL.clueShown = true;
      clue.textContent = node.hint || "";
      clue.classList.add("show");
      btn.style.display = "none";
      TRACK.push({ type: "wordle_clue", section: "s-wordle", after: WL.guesses.length });
    };
    wlPaintClue();
    $("#wl-after").innerHTML = "";
    $("#wl-after").classList.remove("show");
    wlBuildKeyboard();
    wlDrawBoard();
    if (WL.done) {
      var wonAlready = WL.guesses[WL.guesses.length - 1] === WL.answer;
      wlToast(wonAlready ? "You got it! 🎉" : "The word was " + WL.answer);
      wlFinish(wonAlready);
    }
    if (!WL.keysBound) {
      WL.keysBound = true;
      document.addEventListener("keydown", function (ev) {
        if (ev.metaKey || ev.ctrlKey || ev.altKey || ev.isComposing) return;
        // THE BUG: this listener was global, so every letter typed into the
        // Summer Check-In or the feedback box also went into the Wordle row.
        // Five characters later the row was full of junk and every real guess
        // keystroke was silently ignored - which from the other side of the
        // screen just looks like "I can't type."
        if (typingInAField(ev.target)) return;
        // Sudoku owns the keyboard while one of its cells is focused. Without
        // this, Backspace would erase a Sudoku square AND delete a Wordle
        // letter in the same keystroke - the same class of bug as above.
        if (inSection(ev.target, "s-sudoku")) return;
        if (inSection(ev.target, "s-crossword")) return;
        if (ev.key === "Enter") wlKey("ENTER");
        else if (ev.key === "Backspace") wlKey("BACK");
        else if (ev.key === "Escape") { WL.current = ""; wlToast(""); wlDrawBoard(); }
        else if (/^[a-zA-Z]$/.test(ev.key)) wlKey(ev.key.toUpperCase());
      });
    }
  }

  // ---------- connections ----------
  var CN = { groups: [], tiles: [], selected: [], solved: [], mistakes: 0,
             done: false, hints: [] };

  // A hint names one category, so you know WHAT to look for without being told
  // which four words. It unlocks only after a wrong guess.
  //
  // It names the HARDEST unsolved group, not the easiest. Naming the easy one
  // is not a hint at all - on a real board, "one group is TYPES OF TREES"
  // hands over OAK, PINE, MAPLE and BIRCH in one tap, because for a plain
  // category the name IS the answer. The tricky group is the one she is
  // actually stuck on, and its name is a genuine nudge: knowing "one group is
  // HIDDEN VEHICLE INSIDE" still leaves her to find CARPET, TRAINER, CABIN
  // and VANISH among sixteen tiles.
  function cnHintable() {
    var out = [];
    for (var i = 0; i < CN.groups.length; i++) {
      if (CN.solved.indexOf(i) !== -1) continue;
      if (CN.hints.indexOf(i) !== -1) continue;
      out.push(i);
    }
    out.sort(function (a, b) {
      return (CN.groups[b].difficulty || 1) - (CN.groups[a].difficulty || 1);
    });
    return out;
  }

  function cnPaintHints() {
    var btn = $("#cn-hint-btn"), box = $("#cn-hints");
    if (!btn || !box) return;

    box.innerHTML = "";
    CN.hints.forEach(function (gi) {
      var g = CN.groups[gi];
      if (!g) return;
      var row = el("div", "cn-hint-row");
      row.appendChild(el("span", "cn-hint-tag", "One group is"));
      row.appendChild(el("b", null, g.name));
      box.appendChild(row);
    });

    if (CN.done) { btn.style.display = "none"; return; }
    btn.style.display = "";
    var left = cnHintable().length;
    if (CN.mistakes < 1) {
      btn.disabled = true;
      btn.textContent = "Hint unlocks after a wrong guess";
    } else if (!left) {
      btn.disabled = true;
      btn.textContent = "No more hints";
    } else {
      btn.disabled = false;
      btn.textContent = CN.hints.length ? "Another hint" : "Stuck? Get a hint";
    }
  }

  function cnHint() {
    if (CN.done || CN.mistakes < 1) return;
    var next = cnHintable()[0];
    if (next === undefined) return;
    CN.hints.push(next);
    cnSave();
    TRACK.push({ type: "conn_hint", section: "s-conn",
                 after_mistakes: CN.mistakes });
    cnDraw();
  }

  function cnGroupOf(word) {
    for (var i = 0; i < CN.groups.length; i++) {
      if (CN.groups[i].words.indexOf(word) !== -1) return i;
    }
    return -1;
  }

  function cnToast(msg) { $("#cn-toast").textContent = msg || ""; }

  function cnDraw() {
    var grid = $("#cn-grid");
    grid.innerHTML = "";
    CN.solved.forEach(function (gi) {
      var g = CN.groups[gi];
      var band = el("div", "conn-solved d" + (g.difficulty || 1));
      band.appendChild(el("div", "name", g.name));
      band.appendChild(el("div", "words", g.words.join(", ")));
      grid.appendChild(band);
    });
    CN.tiles.forEach(function (w) {
      if (CN.solved.indexOf(cnGroupOf(w)) !== -1) return;
      var b = el("button", "conn-tile", w);
      if (CN.selected.indexOf(w) !== -1) b.classList.add("selected");
      b.disabled = CN.done;
      b.addEventListener("click", function () {
        var at = CN.selected.indexOf(w);
        if (at !== -1) CN.selected.splice(at, 1);
        else if (CN.selected.length < 4) CN.selected.push(w);
        cnToast("");
        cnDraw();
      });
      grid.appendChild(b);
    });

    var dots = $("#cn-dots");
    dots.innerHTML = "";
    for (var i = 0; i < 4; i++) {
      dots.appendChild(el("span", "dot" + (i < CN.mistakes ? " used" : "")));
    }
    $("#cn-submit").disabled = CN.selected.length !== 4 || CN.done;
    $("#cn-clear").disabled = !CN.selected.length || CN.done;
    cnPaintHints();
  }

  function cnSave() {
    store("conn", { solved: CN.solved, mistakes: CN.mistakes, done: CN.done,
                    hints: CN.hints });
  }

  function cnSubmit() {
    if (CN.selected.length !== 4) return;
    var counts = {};
    CN.selected.forEach(function (w) {
      var gi = cnGroupOf(w);
      counts[gi] = (counts[gi] || 0) + 1;
    });
    var best = 0, bestGi = -1;
    Object.keys(counts).forEach(function (gi) {
      if (counts[gi] > best) { best = counts[gi]; bestGi = parseInt(gi, 10); }
    });

    if (best === 4) {
      CN.solved.push(bestGi);
      CN.selected = [];
      if (CN.solved.length === 4) {
        CN.done = true;
        var cst = STREAK.win("groups");
        cnToast("All four! Brilliant. 🌟");
        paintStreak("groups", "cn-streak");
        TRACK.push({ type: "conn_result", section: "s-conn", solved: true,
                     mistakes: CN.mistakes, streak: cst.streak });
      }
      else cnToast("Correct!");
    } else {
      CN.mistakes++;
      if (best === 3) cnToast("So close - one away!");
      else cnToast("Not quite. Try again.");
      if (CN.mistakes >= 4) {
        CN.done = true;
        CN.groups.forEach(function (_, i) {
          if (CN.solved.indexOf(i) === -1) CN.solved.push(i);
        });
        CN.selected = [];
        cnToast("Out of tries - here are the answers.");
        TRACK.push({ type: "conn_result", section: "s-conn", solved: false, mistakes: CN.mistakes });
      }
    }
    cnSave();
    cnDraw();
  }

  function renderConnections() {
    var c = DATA.connections || {};
    CN.groups = (c.groups || []).map(function (g) {
      return { name: g.name, difficulty: g.difficulty || 1, words: g.words.map(function (w) { return String(w).toUpperCase(); }) };
    });
    var all = [];
    CN.groups.forEach(function (g) { all = all.concat(g.words); });
    CN.tiles = seededShuffle(all, DATA.date);
    CN.selected = []; CN.solved = []; CN.mistakes = 0; CN.done = false;
    CN.hints = [];

    var saved = load("conn");
    if (saved && Array.isArray(saved.solved)) {
      CN.solved = saved.solved;
      CN.mistakes = saved.mistakes || 0;
      CN.done = !!saved.done;
      CN.hints = Array.isArray(saved.hints) ? saved.hints : [];
    }
    $("#cn-submit").addEventListener("click", cnSubmit);
    $("#cn-hint-btn").addEventListener("click", cnHint);
    $("#cn-clear").addEventListener("click", function () { CN.selected = []; cnToast(""); cnDraw(); });
    $("#cn-shuffle").addEventListener("click", function () {
      CN.tiles = seededShuffle(CN.tiles, String(Math.random()));
      cnDraw();
    });
    cnDraw();
  }

  // ---------- feedback ----------
  function initFeedback() {
    var rating = null;
    var msg = $("#fb-msg"), fav = $("#fb-fav"), send = $("#fb-send");
    var count = $("#fb-count"), done = $("#fb-done");
    if (!msg || !send) return;

    document.querySelectorAll(".rate").forEach(function (b) {
      b.addEventListener("click", function () {
        rating = (rating === b.dataset.rating) ? null : b.dataset.rating;
        document.querySelectorAll(".rate").forEach(function (x) {
          x.setAttribute("aria-pressed", String(x.dataset.rating === rating));
        });
      });
    });

    msg.addEventListener("input", function () {
      count.textContent = (1000 - msg.value.length) + " left";
    });

    send.addEventListener("click", function () {
      if (!rating && !msg.value.trim() && !fav.value) {
        done.textContent = "Pick a face or write something first.";
        done.className = "fb-done show err";
        return;
      }
      send.disabled = true;
      send.textContent = "Sending…";
      fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rating: rating, message: msg.value, favourite: fav.value, age: AGE
        })
      })
        .then(function (r) { return r.json(); })
        .then(function (r) {
          if (!r.ok) throw new Error("not saved");
          done.textContent = "Got it — thanks! Dad will see this.";
          done.className = "fb-done show";
          msg.value = ""; fav.value = ""; rating = null;
          count.textContent = "1000 left";
          document.querySelectorAll(".rate").forEach(function (x) {
            x.setAttribute("aria-pressed", "false");
          });
          send.textContent = "Sent";
          setTimeout(function () { send.disabled = false; send.textContent = "Send another"; }, 1500);
        })
        .catch(function () {
          done.textContent = "Couldn't send that — try again in a moment.";
          done.className = "fb-done show err";
          send.disabled = false; send.textContent = "Send it";
        });
    });
  }

  // ---------- sudoku ----------
  // focusWanted stays false until the child actually picks a square, so the
  // page never steals focus (and scrolls itself to the Sudoku) on load.
  var SD = { size: 6, boxR: 2, boxC: 3, given: [], cells: [], sol: [], sel: -1,
             done: false, level: "easy", focusWanted: false };

  // A 6x6 can only be made so hard - below about 12 clues it stops being
  // solvable without guessing at all. So the way up is a bigger grid, and
  // that choice belongs to whoever is playing, not to the age toggle. It
  // sticks between visits and doesn't touch anything else on the page.
  function sdWanted() {
    var pick = lsGet("kd-sd-level");
    if (pick === "easy" || pick === "hard") return pick;
    return AGE === "11" ? "hard" : "easy";
  }

  // Returns {level, pz}, falling back to whichever grid the server did send
  // so a half-built payload downgrades instead of blanking the section.
  function sdPuzzle() {
    var all = DATA.sudoku;
    if (!all) return null;
    var want = sdWanted();
    if (!all[want]) want = (want === "hard") ? "easy" : "hard";
    if (!all[want]) return null;
    return { level: want, pz: all[want] };
  }

  function sdConflicts() {
    // Which filled cells clash with a peer. Shown live - for a 9-year-old,
    // finding out at the end that move six was wrong is just demoralising.
    var n = SD.size, bad = {};
    function scan(idxs) {
      var seen = {};
      idxs.forEach(function (i) {
        var v = SD.cells[i];
        if (!v) return;
        if (seen[v] !== undefined) { bad[i] = 1; bad[seen[v]] = 1; }
        else seen[v] = i;
      });
    }
    var r, c, i, group;
    for (r = 0; r < n; r++) {
      group = []; for (c = 0; c < n; c++) group.push(r * n + c); scan(group);
    }
    for (c = 0; c < n; c++) {
      group = []; for (r = 0; r < n; r++) group.push(r * n + c); scan(group);
    }
    for (var br = 0; br < n; br += SD.boxR) {
      for (var bc = 0; bc < n; bc += SD.boxC) {
        group = [];
        for (var dr = 0; dr < SD.boxR; dr++)
          for (var dc = 0; dc < SD.boxC; dc++) group.push((br + dr) * n + (bc + dc));
        scan(group);
      }
    }
    return bad;
  }

  function sdSave() {
    store("sudoku-" + SD.level, { cells: SD.cells, done: SD.done });
  }

  function sdDraw() {
    var grid = $("#sd-grid");
    if (!grid) return;
    var n = SD.size;
    grid.style.gridTemplateColumns = "repeat(" + n + ", 1fr)";
    grid.className = "sd-grid n" + n;
    // The grid is rebuilt on every keystroke, which throws away the focused
    // element - and losing focus mid-word would end keyboard entry after one
    // digit. So remember whether focus was in here, and put it back after.
    var hadFocus = grid.contains(document.activeElement);
    grid.innerHTML = "";
    var bad = sdConflicts();
    // Roving tabindex: only one cell is in the tab order, so Tab lands you in
    // the grid and the arrow keys do the moving - rather than 81 tab stops.
    var firstEditable = -1;
    for (var f = 0; f < n * n; f++) {
      if (!SD.given[f]) { firstEditable = f; break; }
    }
    var tabCell = (SD.sel >= 0 && !SD.given[SD.sel]) ? SD.sel : firstEditable;
    for (var i = 0; i < n * n; i++) {
      var b = el("button", "sd-cell");
      var r = Math.floor(i / n), c = i % n;
      b.type = "button";
      b.tabIndex = (i === tabCell) ? 0 : -1;
      if (SD.given[i]) b.classList.add("given");
      if (i === SD.sel) b.classList.add("sel");
      if (bad[i] && !SD.given[i]) b.classList.add("bad");
      if ((c + 1) % SD.boxC === 0 && c !== n - 1) b.classList.add("br");
      if ((r + 1) % SD.boxR === 0 && r !== n - 1) b.classList.add("bb");
      b.textContent = SD.cells[i] ? String(SD.cells[i]) : "";
      b.disabled = SD.done;
      b.setAttribute("aria-label",
        "row " + (r + 1) + " column " + (c + 1) + ", " +
        (SD.given[i] ? "given " + SD.cells[i]
                     : SD.cells[i] ? String(SD.cells[i]) : "empty"));
      (function (idx) {
        b.addEventListener("click", function () {
          if (SD.done || SD.given[idx]) return;
          SD.sel = (SD.sel === idx) ? -1 : idx;
          // Safari and Firefox on macOS do NOT focus a <button> when you click
          // it. Without this the square highlighted, the keystrokes went to the
          // page body, and the grid listener never heard them - which looked
          // exactly like "typing doesn't work".
          SD.focusWanted = SD.sel >= 0;
          sdDraw();
        });
      })(i);
      grid.appendChild(b);
    }
    // Put focus on the live square: either it was already in the grid and the
    // rebuild destroyed it, or the child just picked a square and the browser
    // declined to focus it. preventScroll stops the page jumping on every
    // keystroke.
    if (hadFocus || SD.focusWanted) {
      var keep = grid.children[SD.sel >= 0 ? SD.sel : tabCell];
      if (keep && !keep.disabled) {
        try { keep.focus({ preventScroll: true }); } catch (e) { keep.focus(); }
      }
    }

    var pad = $("#sd-pad");
    pad.innerHTML = "";
    for (var v = 1; v <= n; v++) {
      var k = el("button", "sd-key", String(v));
      (function (val) {
        k.addEventListener("click", function () { sdPlace(val); });
      })(v);
      k.disabled = SD.done;
      pad.appendChild(k);
    }
    var er = el("button", "sd-key wide", "Erase");
    er.addEventListener("click", function () { sdPlace(0); });
    er.disabled = SD.done;
    pad.appendChild(er);
  }

  // ---- keyboard entry ----------------------------------------------------
  // Bound to the GRID, not the document. A cell has to be focused for these to
  // fire, which is both the natural mental model and the thing that stops
  // Sudoku and Wordle fighting over Backspace.

  function sdSelect(i) {
    SD.sel = i;
    SD.focusWanted = true;
    sdDraw();
  }

  // Arrows skip over the given numbers, since you can never type into those.
  function sdMove(dr, dc) {
    var n = SD.size;
    if (SD.sel < 0) {
      for (var k = 0; k < n * n; k++) {
        if (!SD.given[k]) { sdSelect(k); return; }
      }
      return;
    }
    var r = Math.floor(SD.sel / n), c = SD.sel % n;
    for (var step = 0; step < n; step++) {
      r += dr; c += dc;
      if (r < 0 || r >= n || c < 0 || c >= n) return;   // at the edge, stay put
      var idx = r * n + c;
      if (!SD.given[idx]) { sdSelect(idx); return; }
    }
  }

  var SD_ARROWS = {
    ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1],
    Up: [-1, 0], Down: [1, 0], Left: [0, -1], Right: [0, 1]   // older browsers
  };

  function sdKey(ev) {
    if (SD.done || ev.metaKey || ev.ctrlKey || ev.altKey) return;
    var k = ev.key;

    if (/^[0-9]$/.test(k)) {
      var v = parseInt(k, 10);
      // On the 6x6 there is no 7, 8 or 9 - swallow them rather than pretend.
      if (v > SD.size) { sdToast("This grid only goes up to " + SD.size); return; }
      sdPlace(v);                       // 0 erases, same as the Erase button
      ev.preventDefault(); ev.stopPropagation();
      return;
    }
    if (k === "Backspace" || k === "Delete" || k === " " || k === "Spacebar") {
      sdPlace(0);
      ev.preventDefault(); ev.stopPropagation();
      return;
    }
    if (SD_ARROWS[k]) {
      sdMove(SD_ARROWS[k][0], SD_ARROWS[k][1]);
      ev.preventDefault(); ev.stopPropagation();
      return;
    }
    if (k === "Escape") {
      SD.sel = -1;
      sdDraw();
      ev.preventDefault(); ev.stopPropagation();
    }
  }

  function sdToast(msg) {
    var t = $("#sd-toast");
    if (t) t.textContent = msg || "";
  }

  function sdPlace(v) {
    if (SD.sel < 0 || SD.done || SD.given[SD.sel]) return;
    sdToast("");           // clear "this grid only goes up to 6"
    SD.cells[SD.sel] = v;
    sdSave();
    sdDraw();
    sdCheck();
  }

  function sdCheck() {
    for (var i = 0; i < SD.cells.length; i++) {
      if (!SD.cells[i] || SD.cells[i] !== SD.sol[i]) return;
    }
    SD.done = true;
    SD.sel = -1;
    sdSave();
    var st = STREAK.win("sudoku");
    $("#sd-toast").textContent = SD.level === "easy"
      ? "Solved it! 🎉 Too easy? Tap 9×9 for the big grid."
      : "Solved it! 🎉";
    paintStreak("sudoku", "sd-streak");
    TRACK.push({ type: "sudoku_result", section: "s-sudoku", solved: true, streak: st.streak });
    sdDraw();
  }

  function renderSudoku() {
    var section = document.getElementById("s-sudoku");
    var got = sdPuzzle();
    if (!got) { if (section) section.style.display = "none"; return; }
    if (section) section.style.display = "";
    var pz = got.pz;

    SD.level = got.level;
    var both = !!((DATA.sudoku || {}).easy && (DATA.sudoku || {}).hard);
    document.querySelectorAll(".sdlvl").forEach(function (b) {
      b.style.display = both ? "" : "none";
      b.setAttribute("aria-pressed", String(b.dataset.sd === SD.level));
      if (!SD.btnsBound) {
        b.addEventListener("click", function () {
          lsSet("kd-sd-level", b.dataset.sd);
          TRACK.push({ type: "sudoku_level", section: "s-sudoku", level: b.dataset.sd });
          renderSudoku();
        });
      }
    });
    SD.btnsBound = true;

    SD.size = pz.size; SD.boxR = pz.box_r; SD.boxC = pz.box_c;
    SD.given = pz.puzzle.map(function (v) { return v !== 0; });
    SD.cells = pz.puzzle.slice();
    SD.sol = String(dec(pz.solution)).split(",").map(Number);
    SD.sel = -1; SD.done = false; SD.focusWanted = false;

    var saved = load("sudoku-" + SD.level);
    if (saved && Array.isArray(saved.cells) && saved.cells.length === SD.cells.length) {
      SD.cells = saved.cells;
      SD.done = !!saved.done;
    }
    if (!SD.keysBound) {
      SD.keysBound = true;
      $("#sd-grid").addEventListener("keydown", sdKey);
    }
    // Choosing the 9x9 sticks for good, so a child who tapped it once out of
    // curiosity gets the big grid every morning afterwards and has no idea
    // why Sudoku suddenly got hard. Say so, plainly, with the way back.
    var note = $("#sd-note");
    if (note) {
      var deflt = AGE === "11" ? "hard" : "easy";
      if (SD.level !== deflt) {
        note.textContent = SD.level === "hard"
          ? "You're on the big 9×9 grid — tap 6×6 above for the smaller one."
          : "You're on the small 6×6 grid — tap 9×9 above for the bigger one.";
        note.style.display = "";
      } else {
        note.style.display = "none";
      }
    }
    $("#sd-hint").textContent = (SD.size === 6
      ? "Fill every row, column and 2x3 box with 1 to 6. "
      : "Fill every row, column and 3x3 box with 1 to 9. ")
      + "Pick a square and type a number, or tap the buttons. Arrow keys move, "
      + "Backspace erases. You never have to guess - every square can be "
      + "worked out.";
    $("#sd-toast").textContent = SD.done ? "Solved it! 🎉" : "";
    paintStreak("sudoku", "sd-streak");
    sdDraw();
  }

  // ---------- mini crossword ----------
  // Same keyboard discipline as the Sudoku: everything is bound to the grid,
  // so a key only counts when a square is focused and the three games can
  // never fight over Backspace.

  var XW = { size: 5, pattern: [], entries: [], sol: [], cells: [],
             sel: -1, dir: "across", done: false, level: "easy",
             focusWanted: false, keysBound: false };

  function xwPuzzle() {
    var all = DATA.crossword;
    if (!all) return null;
    var want = AGE === "11" ? "hard" : "easy";
    return all[want] || all.easy || all.hard || null;
  }

  function xwBlock(i) { return XW.cells[i] === null; }

  // Every entry that passes through a cell, so clicking anywhere knows what
  // word it is part of.
  function xwEntryAt(idx, dir) {
    var n = XW.size, r = Math.floor(idx / n), c = idx % n;
    for (var i = 0; i < XW.entries.length; i++) {
      var e = XW.entries[i];
      if (e.dir !== dir) continue;
      if (e.dir === "across" && e.row === r && c >= e.col && c < e.col + e.len) return e;
      if (e.dir === "down" && e.col === c && r >= e.row && r < e.row + e.len) return e;
    }
    return null;
  }

  function xwCurrent() { return XW.sel < 0 ? null : xwEntryAt(XW.sel, XW.dir); }

  function xwCellsOf(e) {
    var out = [];
    for (var k = 0; k < e.len; k++) {
      out.push(e.dir === "across" ? e.row * XW.size + (e.col + k)
                                  : (e.row + k) * XW.size + e.col);
    }
    return out;
  }

  function xwSave() {
    store("xw-" + XW.level, { cells: XW.cells, done: XW.done });
  }

  function xwNumbers() {
    var map = {};
    XW.entries.forEach(function (e) {
      map[e.row * XW.size + e.col] = e.number;
    });
    return map;
  }

  function xwDraw() {
    var grid = $("#xw-grid");
    if (!grid) return;
    var n = XW.size;
    grid.style.gridTemplateColumns = "repeat(" + n + ", 1fr)";
    var hadFocus = grid.contains(document.activeElement);
    grid.innerHTML = "";
    var nums = xwNumbers();
    var cur = xwCurrent();
    var lit = {};
    if (cur) xwCellsOf(cur).forEach(function (i) { lit[i] = 1; });

    for (var i = 0; i < n * n; i++) {
      var b = el("button", "xw-cell");
      b.type = "button";
      if (xwBlock(i)) {
        b.className = "xw-cell block";
        b.disabled = true;
        b.tabIndex = -1;
        grid.appendChild(b);
        continue;
      }
      b.tabIndex = (i === XW.sel) ? 0 : -1;
      if (lit[i]) b.classList.add("lit");
      if (i === XW.sel) b.classList.add("sel");
      if (nums[i]) {
        var tag = el("span", "num", String(nums[i]));
        b.appendChild(tag);
      }
      b.appendChild(el("span", "ch", XW.cells[i] || ""));
      b.disabled = XW.done;
      (function (idx) {
        b.addEventListener("click", function () {
          if (XW.done) return;
          if (XW.sel === idx) {
            // Second tap on the same square flips across/down, the way the
            // Mini does. Only if there is actually a word the other way.
            var other = XW.dir === "across" ? "down" : "across";
            if (xwEntryAt(idx, other)) XW.dir = other;
          } else {
            XW.sel = idx;
            if (!xwEntryAt(idx, XW.dir)) {
              XW.dir = XW.dir === "across" ? "down" : "across";
            }
          }
          XW.focusWanted = true;
          xwDraw();
        });
      })(i);
      grid.appendChild(b);
    }

    if (hadFocus || XW.focusWanted) {
      var keep = grid.children[XW.sel];
      if (keep && !keep.disabled) {
        try { keep.focus({ preventScroll: true }); } catch (e) { keep.focus(); }
      }
    }
    xwPaintClues();
  }

  function xwPaintClues() {
    var cur = xwCurrent();
    var bar = $("#xw-current");
    if (bar) {
      bar.textContent = cur ? (cur.number + " " + cur.dir + " — " + cur.clue)
                            : "Tap a square to start";
    }
    ["across", "down"].forEach(function (dir) {
      var box = $("#xw-" + dir);
      if (!box) return;
      box.innerHTML = "";
      XW.entries.filter(function (e) { return e.dir === dir; })
        .sort(function (a, b) { return a.number - b.number; })
        .forEach(function (e) {
          var li = el("li", "xw-clue");
          li.appendChild(el("b", null, String(e.number)));
          li.appendChild(document.createTextNode(" " + e.clue));
          if (cur && cur.number === e.number && cur.dir === e.dir) {
            li.classList.add("on");
          }
          if (xwEntryDone(e)) li.classList.add("filled");
          li.addEventListener("click", function () {
            XW.dir = e.dir;
            XW.sel = xwCellsOf(e)[0];
            XW.focusWanted = true;
            xwDraw();
          });
          box.appendChild(li);
        });
    });
  }

  function xwEntryDone(e) {
    return xwCellsOf(e).every(function (i) { return !!XW.cells[i]; });
  }

  function xwStep(delta) {
    // Move within the current word, skipping nothing - a mini is small enough
    // that landing on a filled square and typing over it is what you want.
    var cur = xwCurrent();
    if (!cur) return;
    var cells = xwCellsOf(cur);
    var at = cells.indexOf(XW.sel);
    var next = at + delta;
    if (next >= 0 && next < cells.length) {
      XW.sel = cells[next];
      XW.focusWanted = true;
    }
  }

  function xwMove(dr, dc) {
    var n = XW.size, r = Math.floor(XW.sel / n), c = XW.sel % n;
    for (var s = 0; s < n; s++) {
      r += dr; c += dc;
      if (r < 0 || r >= n || c < 0 || c >= n) return;
      var idx = r * n + c;
      if (!xwBlock(idx)) {
        XW.sel = idx;
        XW.dir = dr !== 0 ? "down" : "across";
        if (!xwEntryAt(idx, XW.dir)) XW.dir = XW.dir === "across" ? "down" : "across";
        XW.focusWanted = true;
        return;
      }
    }
  }

  function xwJumpClue(delta) {
    var cur = xwCurrent();
    var order = XW.entries.slice().sort(function (a, b) {
      if (a.dir !== b.dir) return a.dir === "across" ? -1 : 1;
      return a.number - b.number;
    });
    var at = cur ? order.findIndex(function (e) {
      return e.number === cur.number && e.dir === cur.dir;
    }) : -1;
    var next = order[((at + delta) % order.length + order.length) % order.length];
    if (!next) return;
    XW.dir = next.dir;
    XW.sel = xwCellsOf(next)[0];
    XW.focusWanted = true;
    xwDraw();
  }

  function xwPut(ch) {
    if (XW.sel < 0 || XW.done || xwBlock(XW.sel)) return;
    XW.cells[XW.sel] = ch;
    xwSave();
    if (ch) xwStep(1);
    xwDraw();
    xwCheck();
  }

  function xwErase() {
    if (XW.sel < 0 || XW.done) return;
    if (XW.cells[XW.sel]) {
      XW.cells[XW.sel] = "";
    } else {
      xwStep(-1);
      if (XW.sel >= 0) XW.cells[XW.sel] = "";
    }
    xwSave();
    xwDraw();
  }

  function xwCheck() {
    for (var i = 0; i < XW.cells.length; i++) {
      if (XW.cells[i] === null) continue;          // black square
      if (!XW.cells[i] || XW.cells[i] !== XW.sol[i]) return;
    }
    XW.done = true;
    XW.sel = -1;
    xwSave();
    var st = STREAK.win("crossword");
    $("#xw-toast").textContent = "Finished it! ✏️🎉";
    paintStreak("crossword", "xw-streak");
    TRACK.push({ type: "xword_result", section: "s-crossword", solved: true,
                 streak: st.streak });
    xwDraw();
  }

  function xwKey(ev) {
    if (XW.done || ev.metaKey || ev.ctrlKey || ev.altKey) return;
    var k = ev.key;
    if (/^[a-zA-Z]$/.test(k)) {
      xwPut(k.toUpperCase());
      ev.preventDefault(); ev.stopPropagation();
      return;
    }
    if (k === "Backspace" || k === "Delete") {
      xwErase(); ev.preventDefault(); ev.stopPropagation(); return;
    }
    var arrows = { ArrowUp: [-1, 0], ArrowDown: [1, 0],
                   ArrowLeft: [0, -1], ArrowRight: [0, 1] };
    if (arrows[k]) {
      xwMove(arrows[k][0], arrows[k][1]);
      xwDraw(); ev.preventDefault(); ev.stopPropagation(); return;
    }
    if (k === " " || k === "Spacebar") {
      var other = XW.dir === "across" ? "down" : "across";
      if (XW.sel >= 0 && xwEntryAt(XW.sel, other)) { XW.dir = other; xwDraw(); }
      ev.preventDefault(); ev.stopPropagation(); return;
    }
    if (k === "Tab") {
      xwJumpClue(ev.shiftKey ? -1 : 1);
      ev.preventDefault(); ev.stopPropagation(); return;
    }
    if (k === "Enter") {
      xwJumpClue(1); ev.preventDefault(); ev.stopPropagation();
    }
  }

  function xwBuildKeyboard() {
    var rows = ["QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"];
    var kb = $("#xw-kb");
    if (!kb) return;
    kb.innerHTML = "";
    rows.forEach(function (r, idx) {
      var row = el("div", "kb-row");
      r.split("").forEach(function (ch) {
        var b = el("button", "key", ch);
        b.type = "button";
        b.dataset.key = ch;
        row.appendChild(b);
      });
      if (idx === 2) {
        var d = el("button", "key wide", "Del");
        d.type = "button";
        d.dataset.key = "BACK";
        row.appendChild(d);
      }
      kb.appendChild(row);
    });
    if (!kb.dataset.bound) {
      kb.dataset.bound = "1";
      kb.addEventListener("click", function (ev) {
        var b = ev.target.closest(".key");
        if (!b || XW.done) return;
        b.blur();
        if (b.dataset.key === "BACK") xwErase();
        else xwPut(b.dataset.key);
      });
    }
  }

  function renderCrossword() {
    var section = document.getElementById("s-crossword");
    var pz = xwPuzzle();
    if (!pz) { if (section) section.style.display = "none"; return; }
    if (section) section.style.display = "";

    XW.level = AGE === "11" ? "hard" : "easy";
    XW.size = pz.size;
    XW.pattern = pz.pattern || [];
    XW.entries = (pz.entries || []).slice();
    XW.done = false; XW.sel = -1; XW.dir = "across"; XW.focusWanted = false;

    // null marks a black square; "" is an empty white one.
    var solRows = String(dec(pz.answers)).split("|");
    XW.sol = []; XW.cells = [];
    for (var r = 0; r < XW.size; r++) {
      for (var c = 0; c < XW.size; c++) {
        var ch = (XW.pattern[r] || "")[c];
        XW.sol.push(ch === "#" ? null : (solRows[r] || "")[c]);
        XW.cells.push(ch === "#" ? null : "");
      }
    }

    var saved = load("xw-" + XW.level);
    if (saved && Array.isArray(saved.cells) && saved.cells.length === XW.cells.length) {
      XW.cells = saved.cells;
      XW.done = !!saved.done;
    }

    xwBuildKeyboard();
    if (!XW.keysBound) {
      XW.keysBound = true;
      $("#xw-grid").addEventListener("keydown", xwKey);
      var prev = $("#xw-prev"), next = $("#xw-next");
      if (prev) prev.addEventListener("click", function () { xwJumpClue(-1); });
      if (next) next.addEventListener("click", function () { xwJumpClue(1); });
    }
    $("#xw-toast").textContent = XW.done ? "Finished it! ✏️🎉" : "";
    paintStreak("crossword", "xw-streak");
    xwDraw();
  }

  // ---------- summer check-in ----------
  function jrKey() { return "kd-journal"; }
  function jrAll() {
    try { return JSON.parse(lsGet(jrKey())) || []; } catch (e) { return []; }
  }
  function jrSave(list) { lsSet(jrKey(), JSON.stringify(list.slice(-60))); }

  function jrPaintScrapbook() {
    var box = $("#jr-past");
    if (!box) return;
    var mine = jrAll();
    box.innerHTML = "";
    if (!mine.length) return;
    box.appendChild(el("div", "jr-past-title", "Your summer so far (" + mine.length + " " +
      (mine.length === 1 ? "entry" : "entries") + ")"));
    mine.slice().reverse().slice(0, 6).forEach(function (e) {
      var row = el("div", "jr-past-row");
      row.appendChild(el("span", "jr-past-day", e.day));
      row.appendChild(el("span", "jr-past-text",
        (e.mood ? MOOD_EMOJI[e.mood] + " " : "") + (e.grateful || "")));
      box.appendChild(row);
    });
  }

  var MOOD_EMOJI = { sunny: "☀️", happy: "😄", calm: "😌", tired: "🥱", meh: "😐" };

  function initJournal() {
    var grateful = $("#jr-grateful"), send = $("#jr-send");
    if (!grateful || !send) return;
    var mood = null;

    document.querySelectorAll(".mood").forEach(function (b) {
      b.addEventListener("click", function () {
        mood = (mood === b.dataset.mood) ? null : b.dataset.mood;
        document.querySelectorAll(".mood").forEach(function (x) {
          x.setAttribute("aria-pressed", String(x.dataset.mood === mood));
        });
      });
    });

    var done = $("#jr-done");
    var already = jrAll().some(function (e) { return e.day === DATA.date && e.age === AGE; });
    if (already) {
      done.textContent = "You already checked in today. Write again if you like!";
      done.className = "jr-done show";
    }

    send.addEventListener("click", function () {
      if (!grateful.value.trim() && !mood) {
        done.textContent = "Pick how you're feeling, or write something 🙂";
        done.className = "jr-done show err";
        return;
      }
      send.disabled = true; send.textContent = "Saving…";
      var entry = { grateful: grateful.value, mood: mood, age: AGE, day: DATA.date };
      fetch("/api/journal", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(entry)
      })
        .then(function (r) { return r.json(); })
        .then(function (r) {
          if (!r.ok) throw new Error("not saved");
          // Keep a copy on this device so they can read their own summer back.
          var mine = jrAll(); mine.push(entry); jrSave(mine);
          done.textContent = "Saved. Dad can see it — and it is in your summer list below.";
          done.className = "jr-done show";
          grateful.value = "";
          mood = null;
          document.querySelectorAll(".mood").forEach(function (x) {
            x.setAttribute("aria-pressed", "false");
          });
          jrPaintScrapbook();
          send.textContent = "Saved";
          setTimeout(function () { send.disabled = false; send.textContent = "Add another"; }, 1400);
        })
        .catch(function () {
          done.textContent = "Couldn't save that — try again in a moment.";
          done.className = "jr-done show err";
          send.disabled = false; send.textContent = "Save it";
        });
    });
    jrPaintScrapbook();
  }

  // ---------- boot ----------
  function setAge(age) {
    AGE = age;
    lsSet("kd-age", age);
    if (DATA) TRACK.push({ type: "age_switch" });
    document.querySelectorAll(".agebtn").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.age === age));
    });
    if (DATA) { renderPuzzles(); renderSudoku(); renderWordle(); renderCrossword(); }
  }

  // Highlight the nav pill for whichever section is currently in view, and
  // keep that pill scrolled into view on narrow screens.
  // Time is attributed to whichever section the scrollspy considers active, so
  // two sections visible at once on a wide screen don't both bank the seconds.
  var DWELL = { section: null, since: 0, paused: false };

  function dwellSwitch(nextId) {
    var now = Date.now();
    if (DWELL.section && !DWELL.paused) {
      var secs = (now - DWELL.since) / 1000;
      // under a second is scroll-through, not reading
      if (secs >= 1) {
        TRACK.push({ type: "view", section: DWELL.section, seconds: secs });
      }
    }
    DWELL.section = nextId;
    DWELL.since = now;
  }

  function initDwell() {
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        dwellSwitch(DWELL.section);   // bank what we have
        DWELL.paused = true;
      } else {
        DWELL.paused = false;
        DWELL.since = Date.now();
      }
    });
    function finish() {
      dwellSwitch(null);
      TRACK.push({ type: "session", seconds: TRACK.elapsed() });
      TRACK.flush(true);
    }
    window.addEventListener("pagehide", finish);
    window.addEventListener("beforeunload", finish);
    setInterval(function () {
      // periodic partial flush so a crash or a kill doesn't lose the visit
      if (DWELL.section && !DWELL.paused) dwellSwitch(DWELL.section);
      TRACK.flush(false);
    }, 30000);
  }

  function initScrollSpy() {
    var links = Array.prototype.slice.call(document.querySelectorAll(".nav a"));
    var sections = links
      .map(function (a) { return document.querySelector(a.getAttribute("href")); })
      .filter(Boolean);
    if (!sections.length || !("IntersectionObserver" in window)) return;

    var visible = {};
    var obs = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { visible[e.target.id] = e.isIntersecting ? e.intersectionRatio : 0; });
      var bestId = null, best = 0;
      sections.forEach(function (s) {
        if ((visible[s.id] || 0) > best) { best = visible[s.id]; bestId = s.id; }
      });
      if (bestId && bestId !== DWELL.section) dwellSwitch(bestId);
      links.forEach(function (a) {
        var on = bestId && a.getAttribute("href") === "#" + bestId;
        a.classList.toggle("active", !!on);
        if (on && a.parentNode.scrollWidth > a.parentNode.clientWidth) {
          var p = a.parentNode;
          var want = a.offsetLeft - (p.clientWidth - a.offsetWidth) / 2;
          p.scrollTo({ left: Math.max(0, want), behavior: "smooth" });
        }
      });
    }, { rootMargin: "-70px 0px -55% 0px", threshold: [0, 0.25, 0.5, 1] });

    sections.forEach(function (s) { obs.observe(s); });
  }

  function renderAll() {
    $("#date").textContent = DATA.date_pretty || DATA.date;
    // With the 8pm rollover the evening shows TOMORROW's page. Without saying
    // so, doing the puzzle at 8:30pm and again at 9am looks like a repeat -
    // which is exactly what happened.
    try {
      var localToday = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
        .toISOString().slice(0, 10);
      var ahead = $("#ahead");
      if (ahead) {
        if (DATA.date > localToday) {
          ahead.textContent = "You're getting tomorrow's page early - it stays this way until 8pm tomorrow";
          ahead.style.display = "";
        } else {
          ahead.style.display = "none";
        }
      }
    } catch (e) {}
    $("#content").style.display = "";
    $("#loading").style.display = "none";
    renderNews();
    renderSports();
    renderLocal();
    renderWord();
    renderPuzzles();
    renderWordle();
    renderConnections();
    renderSudoku();
    renderCrossword();
    paintStreak("wordle", "wl-streak");
    paintStreak("groups", "cn-streak");
    renderHistory();
    renderJoke();
    renderStory();
    initScrollSpy();
    initDwell();
    initFeedback();
    initJournal();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".agebtn").forEach(function (b) {
      b.addEventListener("click", function () { setAge(b.dataset.age); });
    });
    setAge(AGE);

    fetch("/api/today")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (d) { DATA = d; renderAll(); })
      .catch(function (err) {
        $("#loading").textContent =
          "Could not load today's page (" + err.message + "). Try refreshing in a minute.";
      });
  });
})();
