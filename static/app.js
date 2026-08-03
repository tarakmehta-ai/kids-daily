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
    ans.appendChild(el("div", "a", "Answer: " + dec(node.answer)));
    if (node.solution) ans.appendChild(el("div", "s", dec(node.solution)));
    btn.addEventListener("click", function () {
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
    var p = el("div", "punch", dec(j.punchline));
    var b = el("button", "reveal", "Tell me!");
    b.addEventListener("click", function () {
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
  var WL = { answer: "", guesses: [], current: "", done: false };

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
        e.dataset.key = "ENTER";
        row.appendChild(e);
      }
      r.split("").forEach(function (ch) {
        var b = el("button", "key", ch);
        b.dataset.key = ch;
        row.appendChild(b);
      });
      if (idx === 2) {
        var d = el("button", "key wide", "Del");
        d.dataset.key = "BACK";
        row.appendChild(d);
      }
      kb.appendChild(row);
    });
    kb.addEventListener("click", function (ev) {
      var b = ev.target.closest(".key");
      if (b) wlKey(b.dataset.key);
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
    // felt too easy. It is now behind a button, so asking for it is a choice.
    var clue = $("#wl-hint"), btn = $("#wl-clue-btn");
    clue.textContent = "";
    clue.classList.remove("show");
    btn.style.display = "";
    btn.textContent = "Stuck? Get a clue";
    btn.onclick = function () {
      clue.textContent = node.hint || "";
      clue.classList.add("show");
      btn.style.display = "none";
    };
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
      if (ev.metaKey || ev.ctrlKey || ev.altKey) return;
      if (ev.key === "Enter") wlKey("ENTER");
      else if (ev.key === "Backspace") wlKey("BACK");
      else if (/^[a-zA-Z]$/.test(ev.key)) wlKey(ev.key.toUpperCase());
    });
    }
  }

  // ---------- connections ----------
  var CN = { groups: [], tiles: [], selected: [], solved: [], mistakes: 0, done: false };

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
  }

  function cnSave() {
    store("conn", { solved: CN.solved, mistakes: CN.mistakes, done: CN.done });
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

    var saved = load("conn");
    if (saved && Array.isArray(saved.solved)) {
      CN.solved = saved.solved;
      CN.mistakes = saved.mistakes || 0;
      CN.done = !!saved.done;
    }
    $("#cn-submit").addEventListener("click", cnSubmit);
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
  var SD = { size: 6, boxR: 2, boxC: 3, given: [], cells: [], sol: [], sel: -1, done: false, level: "easy" };

  function sdPuzzle() {
    var all = DATA.sudoku;
    if (!all) return null;
    return all[AGE === "11" ? "hard" : "easy"] || null;
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
    grid.innerHTML = "";
    var bad = sdConflicts();
    for (var i = 0; i < n * n; i++) {
      var b = el("button", "sd-cell");
      var r = Math.floor(i / n), c = i % n;
      if (SD.given[i]) b.classList.add("given");
      if (i === SD.sel) b.classList.add("sel");
      if (bad[i] && !SD.given[i]) b.classList.add("bad");
      if ((c + 1) % SD.boxC === 0 && c !== n - 1) b.classList.add("br");
      if ((r + 1) % SD.boxR === 0 && r !== n - 1) b.classList.add("bb");
      b.textContent = SD.cells[i] ? String(SD.cells[i]) : "";
      b.disabled = SD.done;
      (function (idx) {
        b.addEventListener("click", function () {
          if (SD.done || SD.given[idx]) return;
          SD.sel = (SD.sel === idx) ? -1 : idx;
          sdDraw();
        });
      })(i);
      grid.appendChild(b);
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

  function sdPlace(v) {
    if (SD.sel < 0 || SD.done || SD.given[SD.sel]) return;
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
    $("#sd-toast").textContent = "Solved it! 🎉";
    paintStreak("sudoku", "sd-streak");
    TRACK.push({ type: "sudoku_result", section: "s-sudoku", solved: true, streak: st.streak });
    sdDraw();
  }

  function renderSudoku() {
    var section = document.getElementById("s-sudoku");
    var pz = sdPuzzle();
    if (!pz) { if (section) section.style.display = "none"; return; }
    if (section) section.style.display = "";

    SD.level = AGE === "11" ? "hard" : "easy";
    SD.size = pz.size; SD.boxR = pz.box_r; SD.boxC = pz.box_c;
    SD.given = pz.puzzle.map(function (v) { return v !== 0; });
    SD.cells = pz.puzzle.slice();
    SD.sol = String(dec(pz.solution)).split(",").map(Number);
    SD.sel = -1; SD.done = false;

    var saved = load("sudoku-" + SD.level);
    if (saved && Array.isArray(saved.cells) && saved.cells.length === SD.cells.length) {
      SD.cells = saved.cells;
      SD.done = !!saved.done;
    }
    $("#sd-hint").textContent = (SD.size === 6
      ? "Fill every row, column and 2x3 box with 1 to 6. "
      : "Fill every row, column and 3x3 box with 1 to 9. ")
      + "You never have to guess - every square can be worked out.";
    $("#sd-toast").textContent = SD.done ? "Solved it! 🎉" : "";
    paintStreak("sudoku", "sd-streak");
    sdDraw();
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
    if (DATA) { renderPuzzles(); renderSudoku(); renderWordle(); }
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
