import json
import os
import re
import threading
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parents[2] / ".env")  # before auth reads JWT_SECRET

from esalab import auth, db, mcp_server, share  # noqa: E402
from esalab.agent import Agent  # noqa: E402
from esalab.lookup import lookup, throttled  # noqa: E402
from esalab.pipeline import Jobs, activity, single_reference  # noqa: E402

@asynccontextmanager
async def lifespan(app):
    resume_single_tasks()
    if os.environ.get("ESALAB_CRON", "1") != "0":
        threading.Thread(target=_cron, daemon=True).start()
    async with mcp_server.server.session_manager.run():  # the mounted MCP app's own lifespan is not run by Starlette
        yield


app = FastAPI(title="esalab reference tool", lifespan=lifespan)
JOBS = Jobs()


def _cron():
    while True:
        try:
            JOBS.cron()
        except Exception:
            traceback.print_exc()
        time.sleep(3600)
auth.ensure_admin()
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class Credentials(BaseModel):
    username: str
    password: str


class Query(BaseModel):
    query: str
    meta: dict | None = None  # a candidate the user picked from /api/search; otherwise the server looks the query up


class Research(BaseModel):
    index: int
    query: str


class Choice(BaseModel):
    index: int
    choice: int | None = None  # index into item.meta.candidates
    keep: bool = False  # keep the original entry's data
    meta: dict | None = None  # a result of /research the user picked


class Skip(BaseModel):
    indexes: list[int]
    skip: bool = True


class Block(BaseModel):
    heading: int | None = None
    paras: list[int] = []
    entries: list[str] | None = None  # given: entry k replaces paragraph paras[k]; the rest are appended
    append: bool = False  # no list in the document: add a References section at the end


class Split(BaseModel):
    text: str


@app.get("/")
def index():  # the UI lives in esa-ref-frontend; this container is API only
    return {"service": "esa-ref-backend", "docs": "/docs"}


# Web / curl calls worth a line in the admin timeline (polling GETs are not): method, path pattern -> kind.
API_KINDS = [("POST", r"/api/jobs/[^/]+/(research|choose|skip)$", "review"), ("POST", r"/api/jobs/[^/]+/continue$", "continue"),
             ("POST", r"/api/jobs/[^/]+/(block|split)$", "block"), ("DELETE", r"/api/jobs/[^/]+$", "delete"), ("GET", r"/api/jobs/[^/]+/result\.docx$", "download"),
             ("POST", r"/api/jobs/[^/]+/share$", "share"), ("POST", r"/api/search$", "search"), ("POST", r"/api/reference$", "single"), ("POST", r"/api/token$", "token"), ("PUT", r"/api/me$", "settings")]


@app.middleware("http")
async def log_api(request, call_next):
    resp = await call_next(request)
    path = request.url.path
    kind = next((k for m, pat, k in API_KINDS if m == request.method and re.match(pat, path)), None)
    if kind and resp.status_code < 400:
        try:
            user = auth.current_user(request)
        except HTTPException:
            return resp
        via = "cli" if request.headers.get("user-agent", "").startswith("curl") else "web"  # shortcut: curl = the MCP upload recipe, until MCP uploads itself
        db.event(user, via, kind, kind if kind == "delete" else path.rsplit("/", 1)[-1].split(".")[0])  # detail: the action segment of the path
    return resp


@app.post("/api/register", status_code=201)
def register(c: Credentials):
    token = auth.register(c.username, c.password)
    db.event(c.username.strip(), "web", "register")
    return {"token": token, "username": c.username.strip()}


@app.post("/api/login")
def login(c: Credentials):
    token = auth.login(c.username, c.password)
    db.event(c.username.strip(), "web", "login")
    return {"token": token, "username": c.username.strip()}


DEFAULT_AUTHOR = "ESALab-RefBot"


class Prefs(BaseModel):
    author: str = ""


@app.get("/api/me")
def me(user: str = auth.User):
    with db.connect() as con:
        row = con.execute("SELECT author, tour FROM prefs WHERE username=?", (user,)).fetchone()
    return {"username": user, "admin": user in auth.ADMINS, "author": (row[0] if row else "") or "", "tour": row[1] if row else None}


@app.put("/api/me")
def save_prefs(p: Prefs, user: str = auth.User):
    """Per-user defaults; author = the name prefilled in the Word revision author field."""
    with db.connect() as con:
        con.execute("INSERT INTO prefs (username, author) VALUES (?,?) ON CONFLICT(username) DO UPDATE SET author=excluded.author", (user, p.author.strip()[:64]))
    return me(user)


TOUR_STAGES = ("settings", "lookup", "work", "done")


class Tour(BaseModel):
    stage: str


def set_tour(username: str, stage: str):
    if stage not in TOUR_STAGES:
        raise HTTPException(400, f"stage must be one of {', '.join(TOUR_STAGES)}")
    with db.connect() as con:
        con.execute("INSERT INTO prefs (username, tour) VALUES (?,?) ON CONFLICT(username) DO UPDATE SET tour=excluded.tour", (username, stage))
    db.event(username, "web", "tour", stage)
    return {"username": username, "tour": stage}


@app.put("/api/me/tour")
def my_tour(t: Tour, user: str = auth.User):
    """Onboarding progress: the station the user has reached (settings -> lookup -> work -> done)."""
    return set_tour(user, t.stage)


@app.put("/api/admin/users/{username}/tour")
def user_tour(username: str, t: Tour, user: str = auth.Admin):
    return set_tour(username, t.stage)


@app.get("/api/health")
def health(user: str = auth.User):
    a = Agent()
    return {"opencode": a.healthy(), "opencode_url": a.base, "model": a.model, "throttled": throttled()}


@app.get("/api/jobs")
def list_jobs(user: str = auth.User):
    return JOBS.list(user)


@app.post("/api/jobs")
async def create_job(file: UploadFile = File(...), mode: str = Form("smart"), titles: str = Form(""),
                     author: str = Form(""), review: str = Form("true"), user: str = auth.User):
    if mode not in ("smart", "fix", "add"):
        raise HTTPException(400, "mode must be smart, fix or add")
    # a str, not bool: FastAPI turns a *missing* bool form field into False (checkbox semantics), we want the pause by default
    job = JOBS.create(docx=await file.read(), filename=file.filename or "document.docx", mode=mode,
                      titles=titles.splitlines(), author=author.strip() or DEFAULT_AUTHOR, user=user, review=review.lower() not in ("false", "0", "no"))
    return {"id": job.id}


def _waiting(job_id: str, user: str):
    job = JOBS.get(job_id, user)
    if not job or job.state["status"] != "waiting":
        raise HTTPException(409, "job is not waiting for review")
    return job


@app.post("/api/jobs/{job_id}/research")
def job_research(job_id: str, r: Research, user: str = auth.User):
    return _waiting(job_id, user).research(r.index, r.query)


@app.post("/api/jobs/{job_id}/choose")
def job_choose(job_id: str, c: Choice, user: str = auth.User):
    try:
        return _waiting(job_id, user).choose(c.index, c.choice, c.keep, c.meta)
    except (IndexError, TypeError):
        raise HTTPException(400, "no such candidate")


@app.post("/api/jobs/{job_id}/skip")
def job_skip(job_id: str, s: Skip, user: str = auth.User):
    job = _waiting(job_id, user)
    if any(not 0 <= i < len(job.state["items"]) for i in s.indexes):
        raise HTTPException(400, "no such entry")
    job.skip(s.indexes, s.skip)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/continue", status_code=202)
def job_continue(job_id: str, user: str = auth.User):
    try:
        _waiting(job_id, user).resume()
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"id": job_id}


@app.post("/api/jobs/{job_id}/block", status_code=202)
def job_block(job_id: str, b: Block, user: str = auth.User):
    """Answer the 'where is the reference list' question of a job waiting at the extract stage."""
    try:
        _waiting(job_id, user).set_block(b.heading, b.paras, b.entries, b.append)
    except ValueError as e:
        raise HTTPException(400 if "range" in str(e) else 409, str(e))
    return {"id": job_id}


@app.post("/api/jobs/{job_id}/split")
def job_split(job_id: str, sp: Split, user: str = auth.User):
    """LLM pre-arrangement: a pasted list -> one entry per line, text untouched. The user confirms before anything is written."""
    if not sp.text.strip():
        raise HTTPException(400, "text is empty")
    return {"entries": _waiting(job_id, user).split(sp.text)}


@app.post("/api/search")
def search(q: Query, user: str = auth.User):
    """Pre-search: can the system find this paper? No LLM involved."""
    return lookup(q.query)


def _task_set(rid: str, **cols):
    with db.connect() as con:
        con.execute("UPDATE single_tasks SET " + ", ".join(f"{k}=?" for k in cols) + " WHERE id=?", (*cols.values(), rid))


def _run_single(rid: str, user: str, query: str, meta: dict | None):
    try:
        for step in single_reference(query, meta):
            if isinstance(step, str):
                _task_set(rid, stage=step)
                continue
            with db.connect() as con:
                con.execute("INSERT INTO refs VALUES (?,?,?,?,?,?,?,?,?,?)", (rid, user, time.time(), query, json.dumps(step["meta"], ensure_ascii=False),
                            step["reference"], step["type"], json.dumps(step["issues"], ensure_ascii=False), int(step["check"]["ok"]), json.dumps(step["check"]["problems"], ensure_ascii=False)))
            _task_set(rid, stage="done", result=json.dumps(step | {"id": rid}, ensure_ascii=False))
    except Exception as e:
        _task_set(rid, stage="failed", error=str(e))


def resume_single_tasks():
    """Tasks cut off by a restart start over from lookup (the lookup is cached, the LLM steps redo)."""
    JOBS.fail_orphans()
    with db.connect() as con:
        rows = con.execute("SELECT id, user, query, meta FROM single_tasks WHERE stage NOT IN ('done', 'failed')").fetchall()
    for rid, user, query, meta in rows:
        threading.Thread(target=_run_single, args=(rid, user, query, json.loads(meta) if meta else None), daemon=True).start()


def start_single(user: str, query: str, meta: dict | None) -> str:
    rid = uuid.uuid4().hex[:12]
    with db.connect() as con:
        con.execute("INSERT INTO single_tasks VALUES (?,?,?,?,?,?,?,?)", (rid, user, time.time(), query, json.dumps(meta, ensure_ascii=False) if meta else None, "lookup", None, None))
    threading.Thread(target=_run_single, args=(rid, user, query, meta), daemon=True).start()
    return rid


@app.post("/api/reference", status_code=202)
def reference(q: Query, user: str = auth.User):
    """Starts one reference generation (lookup -> format -> check, own OpenCode sessions) in the background; poll GET /api/reference/{id}."""
    return {"id": start_single(user, q.query, q.meta)}


@app.post("/api/token")
def api_token(user: str = auth.User):
    """A one-year token for MCP clients and curl (the login token lasts a week)."""
    return {"token": auth.token_for(user, ttl=365 * 24 * 3600)}


app.add_route("/mcp", mcp_server.build(JOBS, start_single), methods=["GET", "POST", "DELETE"])


@app.get("/api/reference/{rid}")
def reference_status(rid: str, user: str = auth.User):
    with db.connect() as con:
        row = con.execute("SELECT stage, created, result, error FROM single_tasks WHERE id=? AND user=?", (rid, user)).fetchone()
    if not row:
        raise HTTPException(404, "task not found")
    return {"id": rid, "stage": row[0], "started": row[1], "result": json.loads(row[2]) if row[2] else None, "error": row[3]}


@app.get("/api/references")
def references(user: str = auth.User):
    with db.connect() as con:
        rows = con.execute("SELECT id, created, query, reference, type, issues, check_ok, problems FROM refs WHERE user=? ORDER BY created DESC", (user,)).fetchall()
    return [{"id": r[0], "created": r[1], "query": r[2], "reference": r[3], "type": r[4], "issues": json.loads(r[5]),
             "check": {"ok": bool(r[6]), "problems": json.loads(r[7])}} for r in rows]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, user: str = auth.User):
    s = JOBS.state(job_id, user)
    if not s:
        raise HTTPException(404)
    return s


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, user: str = auth.User):
    if not JOBS.delete(job_id, user):
        raise HTTPException(404, "no such job of yours")


@app.get("/api/admin/stats")
def admin_stats(user: str = auth.Admin):
    return JOBS.stats()


@app.get("/api/admin/activity")
def admin_activity(hours: int = 12, user: str = auth.Admin):
    return activity(min(max(hours, 1), 168))


@app.get("/api/admin/jobs")
def admin_jobs(user: str = auth.Admin):
    return JOBS.list(None)


@app.get("/api/jobs/{job_id}/events")
def job_events(job_id: str, user: str = auth.User):
    job = JOBS.get(job_id, user)
    if not job:
        raise HTTPException(404, "job not running in this server process")

    def gen():
        v = -1
        while True:
            v = job.wait(v)
            yield f"data: {json.dumps(job.state, ensure_ascii=False)}\n\n"
            if job.state["status"] in ("done", "failed"):
                return
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/jobs/{job_id}/share")
def job_share(job_id: str, user: str = auth.User):
    s = JOBS.state(job_id, user)
    if not s or s["status"] != "done":
        raise HTTPException(404, "not finished")
    return share.load(share.create(job_id, user))


@app.get("/api/share/{token}")
def share_get(token: str):
    sh = share.load(token)
    if not sh:
        raise HTTPException(404)
    db.event(sh["user"], "public", "share_view", "")
    return sh


class Hit(BaseModel):
    via: str


@app.post("/api/share/{token}/hit", status_code=204)
def share_hit(token: str, h: Hit):
    sh = share.load(token)
    if not sh or h.via not in share.HIT_TEXT:
        raise HTTPException(404)
    db.event(sh["user"], "public", "share_hit", h.via)


@app.get("/api/share/{token}/card.png")
def share_card(token: str):
    data = share.png(token)
    if not data:
        raise HTTPException(404)
    return Response(data, media_type="image/png", headers={"Cache-Control": "no-cache"})


@app.get("/s/{token}", response_class=HTMLResponse)
def share_page(token: str, request: Request):
    sh = share.load(token)
    if not sh:
        raise HTTPException(404)
    return share.page(sh, share.public_base(request.headers))


@app.get("/api/config")
def config():
    """Public: the front end builds share / MCP links from this when PUBLIC_URL is set, else from its own origin."""
    return {"public_url": os.environ.get("PUBLIC_URL", "").rstrip("/")}


@app.get("/api/jobs/{job_id}/result.docx")
def job_result(job_id: str, user: str = auth.User):
    s, out = JOBS.state(job_id, user), JOBS.output(job_id, user)
    if not out:
        raise HTTPException(404, "not finished")
    name = quote(result_name(s, JOBS.list(user)))
    return Response(out, media_type=DOCX, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"})


def result_name(s: dict, jobs: list[dict]) -> str:
    """<origin>_esaref_<yymmdd>.docx; the n-th finished job of the same file on the same (Taiwan) day gets _n."""
    day = lambda ts: datetime.fromtimestamp(ts, timezone(timedelta(hours=8))).strftime("%y%m%d")  # noqa: E731
    n = sum(1 for j in jobs if j["filename"] == s["filename"] and j["status"] == "done" and j["started"] < s["started"] and day(j["started"]) == day(s["started"]))
    return f"{s['filename'].removesuffix('.docx')}_esaref_{day(s['started'])}{f'_{n}' if n else ''}.docx"
