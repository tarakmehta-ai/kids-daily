"""Kids Daily - FastAPI app (deployed on Render; Dockerfile included).

Endpoints
    GET  /              the site
    GET  /api/today     today's payload (built on first hit, then cached)
    GET  /api/day/{d}   a specific YYYY-MM-DD, if we still have it
    GET  /health        which sources worked, what fell back to the bank
    POST /api/refresh   force a rebuild (needs ADMIN_TOKEN)
    POST /api/track     engagement events from the page (open, validated hard)
    POST /api/feedback  a note from the kids (open, write-only)
    GET  /stats         parent dashboard (needs ADMIN_TOKEN)
    GET  /api/stats.json  the same data as JSON (needs ADMIN_TOKEN)
"""

from __future__ import annotations

import base64
import copy
import logging
import os
import secrets
import threading
from datetime import date

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import analytics
import builder

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("kidsdaily")

app = FastAPI(title="Kids Daily", docs_url=None, redoc_url=None)
STATIC = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# --------------------------------------------------------------------------
# light answer hiding
# --------------------------------------------------------------------------
# Not security - just enough friction that an 11-year-old who opens the network
# tab doesn't get the Wordle answer handed to them. The page decodes with atob.

def _enc(value: str) -> str:
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _hide_answers(payload: dict) -> dict:
    out = copy.deepcopy(payload)
    for key in ("math_puzzle", "logic_puzzle"):
        for level in ("easy", "hard"):
            node = out.get(key, {}).get(level)
            if isinstance(node, dict):
                for field in ("answer", "solution"):
                    if node.get(field):
                        node[field] = _enc(node[field])
    if out.get("wordle", {}).get("word"):
        out["wordle"]["word"] = _enc(out["wordle"]["word"])
    if out.get("joke", {}).get("punchline"):
        out["joke"]["punchline"] = _enc(out["joke"]["punchline"])
    out["_encoded"] = True
    return out


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


@app.get("/api/today")
def api_today(raw: bool = Query(False, description="skip answer encoding")):
    payload = builder.get_day()
    return JSONResponse(payload if raw else _hide_answers(payload))


@app.get("/api/day/{day_str}")
def api_day(day_str: str):
    try:
        day = date.fromisoformat(day_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="use YYYY-MM-DD")
    if day > builder.today():
        raise HTTPException(status_code=400, detail="no peeking at the future")
    cached = builder._read_cache(day) or builder._pull_from_hub(day)
    if not cached:
        raise HTTPException(status_code=404, detail="no archive for that day")
    return JSONResponse(_hide_answers(cached))


@app.get("/health")
def health():
    payload = builder.get_day()
    diag = payload.get("diagnostics", {})
    fell_back = diag.get("fell_back_to_bank", [])
    return {
        "status": "ok" if not fell_back else "degraded",
        "date": payload.get("date"),
        "generated_at": payload.get("generated_at"),
        "api_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-5"),
        "hub_cache": bool(
            os.environ.get("CACHE_DATASET_REPO") and os.environ.get("HF_TOKEN")
        ),
        "sections_using_offline_bank": fell_back,
        "links_mode": diag.get("links_mode"),
        "blocked_by_filter": diag.get("blocked_by_filter", {}),
        "sources": diag.get("sources", {}),
        "llm": diag.get("llm", {}),
    }


@app.post("/api/refresh")
def refresh(token: str = Query(...)):
    _require_admin(token)
    payload = builder.get_day(force=True)
    return {"rebuilt": payload["date"], "diagnostics": payload["diagnostics"]}


# --------------------------------------------------------------------------
# analytics
# --------------------------------------------------------------------------

def _require_admin(token: str) -> None:
    expected = os.environ.get("ADMIN_TOKEN")
    if not expected:
        raise HTTPException(status_code=403, detail="ADMIN_TOKEN is not set")
    # compare_digest avoids leaking the token length through timing
    if not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=403, detail="nope")


@app.post("/api/track")
async def track(request: Request):
    """Open endpoint - the page posts here. Never returns useful information,
    validates hard, and swallows every error so tracking can't break a visit."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": True})
    events = body.get("events") if isinstance(body, dict) else None
    kept = analytics.record(events if isinstance(events, list) else [])
    return JSONResponse({"ok": True, "kept": kept})


@app.post("/api/feedback")
async def feedback(request: Request):
    """Write-only. Notes go to the parent dashboard, never back onto the page."""
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False})
    ok = analytics.record_feedback(body if isinstance(body, dict) else {})
    return JSONResponse({"ok": bool(ok)})


@app.get("/api/stats.json")
def stats_json(token: str = Query(...), day: str | None = Query(None)):
    _require_admin(token)
    if day:
        try:
            d = date.fromisoformat(day)
        except ValueError:
            raise HTTPException(status_code=400, detail="use YYYY-MM-DD")
    else:
        d = analytics.today()
    return {
        "today": analytics.daily(d),
        "overall": analytics.overall(),
        "feedback": analytics.read_feedback(),
    }


@app.get("/stats")
def stats_page(token: str = Query(...)):
    _require_admin(token)
    return FileResponse(os.path.join(STATIC, "stats.html"))


@app.on_event("shutdown")
def flush_stats():
    """Render gives a grace period on spin-down; use it to save the last events."""
    try:
        analytics.flush()
    except Exception:  # noqa: BLE001
        log.exception("stats flush failed")


@app.on_event("startup")
def warm_cache():
    """Build today's page in the background so the first visitor doesn't wait."""

    def _warm():
        try:
            analytics.restore()          # pull stats back after a restart
            analytics.restore_feedback()
            builder.get_day()
            log.info("warm-up complete")
        except Exception:  # noqa: BLE001
            log.exception("warm-up failed")

    threading.Thread(target=_warm, daemon=True).start()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
