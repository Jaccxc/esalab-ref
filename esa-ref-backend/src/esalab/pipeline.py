"""Stateful reference job: extract -> lookup -> (review pause) -> order -> format -> check -> apply, with live progress.
Modes: smart (default: add missing titles, fix all entries, fix citation order), fix (entries only), add (titles only)."""
from __future__ import annotations

import json
import re
import threading
import time
import traceback
import uuid

from esalab import db, order
from esalab.share import HIT_TEXT
from esalab.agent import CHECK_SCHEMA, FORMAT_SCHEMA, PARSE_SCHEMA, SPLIT_SCHEMA, Agent
from esalab.docx_track import Doc
from esalab.lookup import lookup, norm, DOI_RE, IEEE_RE, THROTTLED, _openalex, _semanticscholar

RETAIN_DAYS = 30
PING_TITLE = "Attention is all you need"
STAGES = [("extract", 1), ("lookup", 3), ("review", 0), ("order", 1), ("format", 10), ("check", 10), ("apply", 1)]
TITLE_RE = re.compile(r"[“\"](.+?)[,.]?[”\"]")


# ---- single-entry LLM steps, shared by the docx job and the one-off reference tool -----------------
def format_entry(agent: Agent, original: str, meta: dict | None) -> dict:
    """-> {type, reference, issues, confidence}; runs in its own OpenCode session."""
    prompt = (
        "Format ONE reference entry.\n"
        f"ORIGINAL ENTRY (may be wrong or incomplete): {original}\n"
        f"METADATA: {json.dumps(meta, ensure_ascii=False)}\n"
        "Return the entry without the [n] label."
    )
    out = agent.ask(prompt, FORMAT_SCHEMA, title="format")
    out["reference"] = out["reference"].strip()
    return out


def check_entry(agent: Agent, candidate: str, original: str, meta: dict | None) -> dict:
    """-> {ok, problems, reference}; an independent session so the checker never sees the formatter's reasoning."""
    prompt = (
        "Review ONE formatted entry against the rules. Check author list form, abbreviations, "
        "italics, punctuation, en dashes, month form, Art. no., conference location/date, and "
        "consistency. Return ok=true only if nothing needs changing; otherwise return the corrected entry.\n"
        f"CANDIDATE: {candidate}\nORIGINAL: {original}\n"
        f"METADATA: {json.dumps(meta, ensure_ascii=False)}"
    )
    out = agent.ask(prompt, CHECK_SCHEMA, title="check")
    out["reference"] = (out.get("reference") or candidate).strip() if not out["ok"] else candidate
    return out


def split_entries(agent: Agent, text: str) -> list[str]:
    """A pasted reference list -> one entry per item, untouched: the pre-arrangement a user confirms before the job reads it."""
    prompt = ("Split this reference list into separate entries. One entry per item, in the original order. Do not reformat, "
              "correct, translate or drop anything; only remove a leading number or bullet. Keep every entry's text exactly.\n\n" + text)
    return [e.strip() for e in agent.ask(prompt, SPLIT_SCHEMA, title="split")["entries"] if e.strip()]


def single_reference(query: str, meta: dict | None = None, agent: Agent | None = None):
    """The one-off tool: query (title/DOI/URL) -> lookup (unless meta given) -> format -> check.
    A generator: yields the stage name ("format", "check") before each LLM step, then the result dict."""
    agent = agent or Agent()
    meta = meta or lookup(query)
    yield "format"
    fmt = format_entry(agent, query, meta)
    yield "check"
    chk = check_entry(agent, fmt["reference"], query, meta)
    yield {"meta": meta, "type": fmt.get("type"), "issues": fmt.get("issues", []), "formatted": fmt["reference"],
           "check": {"ok": chk["ok"], "problems": chk.get("problems", [])}, "reference": chk["reference"]}


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, docx: bytes, filename: str, mode: str, titles: list[str], author: str, user: str = "",
                 review: bool = True, agent: Agent | None = None, state: dict | None = None):
        self.docx = docx
        self.agent = agent or Agent()
        self.cond = threading.Condition()
        self.version = 0
        self.stop = threading.Event()  # set by delete(): the worker thread aborts at its next state write
        if state:  # rehydrated from the database (e.g. a job waiting for review across a server restart)
            self.state = state
            self.id = state["id"]
            return
        self.id = uuid.uuid4().hex[:12]
        self.state = {
            "id": self.id, "filename": filename, "mode": mode, "author": author, "titles": titles, "user": user,
            "review": review, "status": "queued", "stage": None, "stage_done": 0, "stage_total": 0,
            "percent": 0, "eta_seconds": None, "elapsed": 0, "started": time.time(),
            "model": self.agent.model, "items": [], "order": None, "log": [], "error": None, "ask": None, "block": None,
        }
        with db.connect() as con:  # persist at once so the job is listed before the worker thread starts
            con.execute("INSERT INTO jobs (id, user, started, state, input) VALUES (?,?,?,?,?)", (self.id, user, self.state["started"], json.dumps(self.state), docx))

    # ---- state helpers -------------------------------------------------
    def _emit(self):
        if self.stop.is_set():
            raise Cancelled()
        self.state["elapsed"] = round(time.time() - self.state["started"], 1)
        with self.cond:
            self.version += 1
            with db.connect() as con:
                con.execute("UPDATE jobs SET state=? WHERE id=? AND deleted IS NULL", (json.dumps(self.state, ensure_ascii=False), self.id))
            self.cond.notify_all()

    def log(self, msg: str):
        self.state["log"].append(f"{time.strftime('%H:%M:%S')} {msg}")
        self._emit()

    def _progress(self, stage: str, done: int, total: int):
        names = [s for s, _ in STAGES]
        finished = sum(wt for name, wt in STAGES if names.index(name) < names.index(stage))
        frac = done / total if total else 1
        pct = (finished + dict(STAGES)[stage] * frac) / sum(wt for _, wt in STAGES)
        self.state.update(stage=stage, stage_done=done, stage_total=total, percent=round(pct * 100, 1))
        el = time.time() - self.state["started"]
        self.state["eta_seconds"] = round(el / pct - el) if pct > 0.05 else None
        self._emit()

    def wait(self, version: int, timeout: float = 15) -> int:
        with self.cond:
            self.cond.wait_for(lambda: self.version != version, timeout=timeout)
            return self.version

    # ---- pipeline ------------------------------------------------------
    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _guarded(self, steps):
        try:
            self.state["status"] = "running"
            if not self.agent.healthy():
                raise RuntimeError(f"opencode server not reachable at {self.agent.base}")
            for step in steps:
                r = step()
                if r == "wait":
                    return
                if r == "done":  # nothing to do (no list, no titles): finish right away
                    break
            self.state["status"] = "done"
            self.state["percent"] = 100
            self.state["eta_seconds"] = 0
            self.log("done")
        except Cancelled:  # the job was deleted while running; its row is already gone
            return
        except Exception as e:  # surfaced to the UI; the job stays inspectable
            self.state["status"] = "failed"
            self.state["error"] = f"{type(e).__name__}: {e}"
            self.log(traceback.format_exc().splitlines()[-1])

    def _run(self):
        self._guarded([self._extract, self._lookup, self._review, self._order, self._format, self._check, self._apply])

    def resume(self):
        """Continue after the user reviewed the located papers."""
        if self.state["status"] != "waiting" or self.state.get("ask"):
            raise ValueError("job is not waiting for review")
        self.state["review"] = False
        threading.Thread(target=self._guarded, args=([self._order, self._format, self._check, self._apply],), daemon=True).start()

    def set_block(self, heading: int | None, paras: list[int], entries: list[str] | None, append: bool = False):
        """The user's answer to the reference-block question; the job reads the entries again and goes on.
        append=True: the document has no list, write a new References section at the end (only the given titles)."""
        if self.state["status"] != "waiting" or not self.state.get("ask"):
            raise ValueError("job is not waiting for the reference block")
        n = len(Doc(self.docx).paras)
        if any(not 0 <= j < n for j in paras) or (heading is not None and not 0 <= heading < n):
            raise ValueError("paragraph index out of range")
        block = {"heading": None, "paras": [], "append": True} if append else {"heading": heading, "paras": sorted(paras)}
        if entries is not None and not append:
            block["entries"] = [e for e in entries if e.strip()]
        self.state["block"], self.state["ask"] = block, None
        self.log("no list in the document: a References section will be appended" if append else
                 f"reference block confirmed: {len(paras)} paragraphs" + (f", {len(block['entries'])} entries given" if entries is not None else ""))
        threading.Thread(target=self._guarded, args=([self._extract, self._lookup, self._review, self._order, self._format, self._check, self._apply],), daemon=True).start()

    def split(self, text: str) -> list[str]:
        return split_entries(self.agent, text)

    def _extract(self):
        self._progress("extract", 0, 1)
        doc = Doc(self.docx, self.state.get("block"))
        items = []
        if self.state["mode"] in ("smart", "fix"):
            found = doc.entries()
            if not found and self.state.get("block") is None:  # nothing readable: stop and ask where the list is
                self.state["ask"] = doc.suggest()
                self.state["status"] = "waiting"
                self.state["eta_seconds"] = None
                self.log(f"no [n] entries found ({self.state['ask']['reason']}): waiting for the user to point at the list")
                return "wait"
            for e in found:
                items.append({"kind": "fix", "index": e["index"], "label": e["label"], "number": int(e["label"][1:-1]),
                              "original": e["text"], "status": "pending"})
        if self.state["mode"] in ("smart", "add"):
            for k, t in enumerate(self.state["titles"], 1):
                if t.strip():
                    items.append({"kind": "add", "index": None, "label": None, "line": k, "original": t.strip(), "status": "pending"})
        if not items:
            if self.state.get("block") is None:
                raise RuntimeError("no [n] entries found under a References heading and no titles given")
            self.log("no entries in the document and no titles given: nothing to do")
            self.state["items"] = []
            return "done"
        self.state["items"] = items
        self.log(f"found {len(items)} entries")
        self._progress("extract", 1, 1)

    def _lookup(self):
        items = self.state["items"]
        for i, it in enumerate(items):
            self._progress("lookup", i, len(items))
            self._lookup_item(it, it["original"] if it["kind"] == "add" else self._title_of(it["original"]))
        self._progress("lookup", len(items), len(items))
        existing = [norm(it["original"]) for it in items if it["kind"] == "fix"]
        for it in items:  # smart mode: a given title that is already in the list is not added again
            if it["kind"] == "add" and self.state["mode"] == "smart":
                t = norm(it["meta"].get("title") or "")
                dup = [n for n, e in enumerate(existing) if t and t in e]
                if dup:
                    it["status"], it["duplicate_of"] = "duplicate", [x for x in items if x["kind"] == "fix"][dup[0]]["number"]
        n = sum(1 for it in items if it["status"] == "duplicate")
        if n:
            self.log(f"{n} given titles already in the list")

    def _lookup_item(self, it: dict, query: str | None):
        hint = it.get("title")  # the entry's own title resolves links that carry no DOI (IEEE Xplore)
        if not hint or "://" in hint or DOI_RE.search(hint):  # an earlier re-query left a link here: go back to the entry text
            hint = self._title_of(it.get("original") or "")
        if not (query and IEEE_RE.search(query)):
            it["title"] = query
        try:
            it["meta"] = lookup(query, hint) if query else {"match": "none", "candidates": []}
        except Exception as e:
            it["meta"] = {"match": "none", "candidates": [], "error": str(e)}
        it["status"] = "looked-up"
        it["uncertain"] = it["meta"].get("match") != "exact"

    def _title_of(self, entry: str) -> str | None:
        m = TITLE_RE.search(entry)
        if m:
            return m.group(1).strip()
        try:
            return self.agent.ask(f"Extract the work's title from this reference entry:\n{entry}", PARSE_SCHEMA, title="parse").get("title")
        except Exception:
            return None

    def _review(self):
        """Pause so the user can confirm the located papers (always, unless review=false was requested)."""
        if not self.state.get("review", True):
            return None
        self._progress("review", 0, 1)
        self.state["status"] = "waiting"
        self.state["eta_seconds"] = None
        self.log(f"waiting for review ({sum(1 for it in self.state['items'] if it.get('uncertain'))} uncertain)")
        return "wait"

    # review actions (called from the API while status == waiting)
    def research(self, index: int, query: str) -> dict:
        """Look the query up for this entry without touching it; the user picks a result via choose(meta=...)."""
        probe = dict(self.state["items"][index])
        self._lookup_item(probe, query)
        return probe["meta"]

    def choose(self, index: int, choice: int | None = None, keep: bool = False, meta: dict | None = None) -> dict:
        it = self.state["items"][index]
        if keep:
            it["meta"] = {"title": it.get("title"), "match": "none", "candidates": [], "kept": True}
        elif meta is not None:
            it["meta"] = {k: v for k, v in meta.items() if k != "error"} | {"match": "exact", "candidates": []}
        else:
            it["meta"] = it["meta"]["candidates"][choice] | {"match": "exact", "candidates": []}
        it["uncertain"] = False
        self._emit()
        return it

    def skip(self, indexes: list[int], skip: bool = True):
        """Skipped entries are left exactly as written (only renumbered); nothing is formatted or checked."""
        for i in indexes:
            self.state["items"][i]["skip"] = skip
        self._emit()

    def _order(self):
        """Citation numbers follow first appearance in the text; placeholders [+k] are resolved here."""
        self._progress("order", 0, 1)
        items = self.state["items"]
        fixes = [it for it in items if it["kind"] == "fix"]
        new = [it["line"] for it in items if it["kind"] == "add" and it["status"] != "duplicate"]
        aliases = {f"+{it['line']}": it["duplicate_of"] for it in items if it.get("duplicate_of")}
        doc = Doc(self.docx, self.state.get("block"))
        p = order.plan(len(fixes), order.cited_sequence(doc.body_texts()) if self.state["mode"] != "add" else [], new, aliases)
        self.state["order"] = p
        number = order.final_numbers(p)
        for it in items:  # final number of every entry that ends up in the list
            if it["kind"] == "fix":
                it["number_final"] = number[it["number"]]
            elif it["status"] != "duplicate":
                it["number_final"] = number[f"+{it['line']}"]
        if not p["ok"]:
            self.log(f"citation order fixed: {len(p['renumber'])} renumbered, {len(p['placeholders'])} placeholders"
                     + (f", unknown {p['unknown']}" if p["unknown"] else ""))
        self._progress("order", 1, 1)

    def _format(self):
        items = [it for it in self.state["items"] if it["status"] != "duplicate" and not it.get("skip")]
        for i, it in enumerate(items):
            self._progress("format", i, len(items))
            try:
                out = format_entry(self.agent, it["original"], it.get("meta"))
                it.update(type=out.get("type"), formatted=out["reference"], issues=out.get("issues", []), status="formatted")
            except Exception as e:
                it.update(status="error", error=str(e))
            self._emit()
        self._progress("format", len(items), len(items))

    def _check(self):
        items = [it for it in self.state["items"] if it.get("formatted")]
        for i, it in enumerate(items):
            self._progress("check", i, len(items))
            try:
                out = check_entry(self.agent, it["formatted"], it["original"], it.get("meta"))
                it["check"] = {"ok": out["ok"], "problems": out.get("problems", [])}
                it["final"] = out["reference"]
                it["status"] = "checked"
            except Exception as e:
                it["check"] = {"ok": False, "problems": [f"checker failed: {e}"]}
                it["final"] = it["formatted"]
            self._emit()
        self._progress("check", len(items), len(items))

    def _apply(self):
        self._progress("apply", 0, 1)
        doc = Doc(self.docx, self.state.get("block"))
        relabel = doc.relabel  # labels were not typed text: every entry is rewritten with one
        items = self.state["items"]
        by_final = {it["number_final"]: it for it in items if it.get("number_final")}
        fixes = sorted((it for it in items if it["kind"] == "fix"), key=lambda it: it["number"])
        repl, add = {}, []
        for pos in range(1, len(by_final) + 1):  # the list in its final order: entry pos goes into paragraph pos
            it = by_final[pos]
            text = it.get("final") or it["original"]
            it["changed"] = (bool(it.get("final")) and it["final"] != it["original"]) or it.get("number_final") != it.get("number")
            if pos <= len(fixes) and fixes[pos - 1]["index"] is not None:
                if it["changed"] or fixes[pos - 1] is not it or relabel:
                    repl[fixes[pos - 1]["index"]] = f"[{pos}]\t{text}"
            else:
                add.append(f"[{pos}]\t{text}")
        p = self.state.get("order") or {"ok": True}
        body_fn = (lambda t: order.rewrite(t, order.final_numbers(p))) if not p["ok"] else None
        out, body_changed = doc.apply(repl, add, self.state["author"], body_fn)
        with db.connect() as con:
            con.execute("UPDATE jobs SET output=? WHERE id=?", (out, self.id))
        self.state["changed"] = len(repl) + len(add) + body_changed
        self.state["body_changed"] = body_changed
        self._progress("apply", 1, 1)


class Jobs:
    def __init__(self):
        self.jobs: dict[str, Job] = {}

    def create(self, **kw) -> Job:
        job = Job(**kw)
        self.jobs[job.id] = job
        job.start()
        return job

    def get(self, job_id: str, user: str) -> Job | None:
        job = self.jobs.get(job_id)
        if job:
            return job if job.state["user"] == user else None
        with db.connect() as con:  # a job left waiting for review by an earlier server run can still be resumed
            row = con.execute("SELECT state, input FROM jobs WHERE id=? AND user=? AND deleted IS NULL", (job_id, user)).fetchone()
        if row and '"status": "waiting"' in row[0]:
            st = json.loads(row[0])
            job = self.jobs[job_id] = Job(row[1], st["filename"], st["mode"], st["titles"], st["author"], user, state=st)
            return job
        return None

    def state(self, job_id: str, user: str) -> dict | None:
        """Live state, or the one persisted by an earlier server run; only the owner's."""
        job = self.get(job_id, user)
        if job:
            return job.state
        with db.connect() as con:
            row = con.execute("SELECT state FROM jobs WHERE id=? AND user=? AND deleted IS NULL", (job_id, user)).fetchone()
        return json.loads(row[0]) if row else None

    def output(self, job_id: str, user: str) -> bytes | None:
        with db.connect() as con:
            row = con.execute("SELECT output FROM jobs WHERE id=? AND user=? AND deleted IS NULL", (job_id, user)).fetchone()
        return row[0] if row else None

    def list(self, user: str | None = None) -> list[dict]:
        """Job summaries newest first; user=None (admin) lists everyone's."""
        with db.connect() as con:
            rows = con.execute("SELECT state FROM jobs WHERE (user=? OR ? IS NULL) AND deleted IS NULL ORDER BY started DESC", (user, user)).fetchall()
        return [summary(json.loads(st)) for (st,) in rows]

    def fail_orphans(self):
        """A restart kills the worker threads; their jobs would otherwise show as running forever."""
        with db.connect() as con:
            for jid, st in con.execute("SELECT id, state FROM jobs").fetchall():
                s = json.loads(st)
                if s["status"] == "running":
                    s.update(status="failed", error="伺服器重啟，工作中斷；請重新上傳")
                    con.execute("UPDATE jobs SET state=? WHERE id=?", (json.dumps(s, ensure_ascii=False), jid))

    def delete(self, job_id: str, user: str) -> bool:
        """Soft: the docx blobs go, the row stays (hidden) so the stats keep its numbers. A running worker stops after the LLM call it is in."""
        with db.connect() as con:
            row = con.execute("SELECT state FROM jobs WHERE id=? AND user=? AND deleted IS NULL", (job_id, user)).fetchone()
            if not row:
                return False
            s = json.loads(row[0])
            if s["status"] in ("queued", "running", "waiting"):
                s.update(status="failed", error="使用者中斷並刪除")
            con.execute("UPDATE jobs SET deleted=?, input=NULL, output=NULL, state=? WHERE id=?", (time.time(), json.dumps(s, ensure_ascii=False), job_id))
        if job := self.jobs.pop(job_id, None):
            job.stop.set()
        return True

    def purge(self, days: int = RETAIN_DAYS) -> int:
        """Drop the upload and the result of finished jobs older than `days` (the row and its numbers stay for the stats).
        A job still waiting for the user is left alone: it can be resumed whenever they come back."""
        cutoff = time.time() - days * 86400
        n = 0
        with db.connect() as con:
            for jid, st in con.execute("SELECT id, state FROM jobs WHERE started < ? AND input IS NOT NULL", (cutoff,)).fetchall():
                s = json.loads(st)
                if s["status"] not in ("done", "failed"):
                    continue
                s["expired"] = True
                con.execute("UPDATE jobs SET input=NULL, output=NULL, state=? WHERE id=?", (json.dumps(s, ensure_ascii=False), jid))
                n += 1
            con.execute("UPDATE shares SET png=NULL WHERE png_at < ?", (cutoff,))  # the card is redrawn on the next view
        if n:
            db.event("system", "cron", "purge", str(n))
        return n

    def cron(self):
        """Hourly tick from the server: purge old files; once a day call the two keyed APIs so the keys stay in use."""
        self.purge()
        with db.connect() as con:
            last = con.execute("SELECT MAX(t) FROM events WHERE kind='ping'").fetchone()[0]
        if last and time.time() - last < 86400:
            return
        for name, fn in (("openalex", _openalex), ("semanticscholar", _semanticscholar)):
            for _ in range(2):  # S2 allows 1 request/s and 429s on a whim; one retry is enough for a signal
                try:
                    ok = bool(fn(PING_TITLE))
                except Exception:  # network down: an exception must not kill the cron thread
                    ok = False
                if ok:
                    break
                time.sleep(2)
            db.event("system", "cron", "ping", f"{name} {'ok' if ok else THROTTLED.get(name, {}).get('status', 'error')}")

    def stats(self) -> dict:
        """Admin dashboard numbers, computed from the job states (small scale: a full scan is fine)."""
        with db.connect() as con:
            users = con.execute("SELECT u.username, u.created, p.tour FROM users u LEFT JOIN prefs p ON p.username=u.username ORDER BY u.created").fetchall()
            states = [json.loads(st) for (st,) in con.execute("SELECT state FROM jobs").fetchall()]
            refs = con.execute("SELECT user, created, type, check_ok FROM refs").fetchall()
            tasks = con.execute("SELECT stage FROM single_tasks").fetchall()
            cache = con.execute("SELECT COUNT(*) FROM lookups").fetchone()[0]
            events = con.execute("SELECT user, via, kind, detail FROM events WHERE via NOT IN ('cron', 'public')").fetchall()
            shares = con.execute("SELECT COUNT(*) FROM shares").fetchone()[0]
            hits = con.execute("SELECT kind, detail FROM events WHERE via='public'").fetchall()
            pings = con.execute("SELECT t, detail FROM events WHERE kind='ping' ORDER BY t DESC LIMIT 2").fetchall()
            purge = con.execute("SELECT t, detail FROM events WHERE kind='purge' ORDER BY t DESC LIMIT 1").fetchone()
            expired = con.execute("SELECT COUNT(*) FROM jobs WHERE input IS NULL AND deleted IS NULL").fetchone()[0]
        done = [s for s in states if s["status"] == "done"]
        day = lambda t: time.strftime("%Y-%m-%d", time.localtime(t))  # noqa: E731
        per_user = {u: {"username": u, "created": c, "tour": t, "jobs": 0, "failed": 0, "entries": 0, "changed": 0, "refs": 0, "last_active": None} for u, c, t in users}
        pu_of = lambda u: per_user.setdefault(u, {"username": u, "created": None, "tour": None, "jobs": 0, "failed": 0, "entries": 0, "changed": 0, "refs": 0, "last_active": None})  # noqa: E731
        per_day, hours = {}, [0] * 24
        for s in states:
            d = per_day.setdefault(day(s["started"]), {"jobs": 0, "done": 0, "failed": 0, "entries": 0, "refs": 0})
            d["jobs"] += 1
            d["entries"] += len(s["items"])
            if s["status"] in ("done", "failed"):
                d[s["status"]] += 1
            hours[time.localtime(s["started"]).tm_hour] += 1
            pu = pu_of(s["user"])
            pu["jobs"] += 1
            pu["failed"] += s["status"] == "failed"
            pu["entries"] += len(s["items"])
            pu["changed"] += s.get("changed") or 0
            pu["last_active"] = max(pu["last_active"] or 0, s["started"])
        for u, created, _, _ in refs:
            per_day.setdefault(day(created), {"jobs": 0, "done": 0, "failed": 0, "entries": 0, "refs": 0})["refs"] += 1
            pu = pu_of(u)
            pu["refs"] += 1
            pu["last_active"] = max(pu["last_active"] or 0, created)
        items = [it for s in states for it in s["items"]]
        checks = [it["check"]["ok"] for s in done for it in s["items"] if it.get("check")]
        matches = [it["meta"].get("match") for s in done for it in s["items"] if it.get("meta")]
        orders = [s["order"] for s in done if s.get("order")]
        by_mode = lambda f: {m: f([s for s in states if s["mode"] == m]) for m in ("smart", "fix", "add")}  # noqa: E731
        avg = lambda xs: round(sum(xs) / len(xs)) if xs else None  # noqa: E731
        return {
            "users": len(users),
            "jobs": {st: sum(1 for s in states if s["status"] == st) for st in ("done", "failed", "running", "waiting", "queued")},
            "modes": by_mode(len),
            "review": {"on": sum(1 for s in states if s.get("review")), "off": sum(1 for s in states if not s.get("review"))},
            "entries": len(items),
            "changed": sum(s.get("changed") or 0 for s in done),
            "avg_seconds": avg([s["elapsed"] for s in done]),
            "seconds_by_mode": by_mode(lambda ss: avg([s["elapsed"] for s in ss if s["status"] == "done"])),
            "check_pass_rate": round(sum(checks) / len(checks), 3) if checks else None,
            "lookup": {m: matches.count(m) for m in ("exact", "fuzzy", "none")},
            "sources": _count(it["meta"].get("source") or "none" for it in items if it.get("meta") and it["meta"].get("match") != "none"),
            "items": {
                "fix": sum(1 for it in items if it["kind"] == "fix"), "add": sum(1 for it in items if it["kind"] == "add"),
                "duplicate": sum(1 for it in items if it["status"] == "duplicate"), "skipped": sum(1 for it in items if it.get("skip")),
                "uncertain": sum(1 for s in done for it in s["items"] if it.get("meta") and it["meta"].get("match") != "exact" and not it["meta"].get("kept")),
                "kept": sum(1 for it in items if (it.get("meta") or {}).get("kept")),
                "with_issues": sum(1 for it in items if it.get("issues")), "check_failed": sum(1 for it in items if it.get("check") and not it["check"]["ok"]),
                "error": sum(1 for it in items if it["status"] == "error"),
            },
            "types": _count(it.get("type") or "unknown" for it in items if it.get("formatted")),
            "order": {"jobs_reordered": sum(1 for p in orders if not p["ok"]), "renumbered": sum(len(p["renumber"]) for p in orders),
                      "placeholders": sum(len(p["placeholders"]) for p in orders), "unknown": sum(len(p["unknown"]) for p in orders)},
            "asks": _count(s["ask"]["reason"] for s in states if s.get("ask")),
            "blocks": _count("append" if s["block"].get("append") else "typed" if s["block"].get("entries") else "picked" for s in states if s.get("block")),
            "failures": {"by_stage": _count(s["stage"] or "queued" for s in states if s["status"] == "failed"),
                         "errors": _count((s["error"] or "").split(":")[0][:60] for s in states if s["status"] == "failed")},
            "single_refs": {"total": len(refs), "check_ok": sum(ok for *_, ok in refs), "types": _count(t or "unknown" for _, _, t, _ in refs),
                            "tasks": _count(st for (st,) in tasks)},
            "cache": cache,
            "shares": {"total": shares, "views": sum(1 for k, _ in hits if k == "share_view"), "hits": _count(HIT_TEXT.get(d, d) for k, d in hits if k == "share_hit")},
            "cron": {"ping": {"t": pings[0][0] if pings else None, "apis": {d.split()[0]: d.split()[1] for _, d in pings}},
                     "purge": {"t": purge[0], "n": int(purge[1])} if purge else None, "expired": expired, "retain_days": RETAIN_DAYS},
            "api": {"via": _count(v for _, v, k, _ in events if k not in ("login", "register", "tour")),
                    "web": _count(API_TEXT.get(d, d) for _, v, k, d in events if v != "mcp" and k not in ("login", "register", "tour")),
                    "mcp": _count(d for _, v, _, d in events if v == "mcp"),
                    "by_user": {u: {"web": sum(1 for x, v, _, _ in events if x == u and v != "mcp"), "mcp": sum(1 for x, v, _, _ in events if x == u and v == "mcp")}
                                for u in sorted({x for x, *_ in events})},
                    "logins": sum(1 for _, _, k, _ in events if k == "login"), "tours": _count(TOUR_TEXT.get(d, d) for _, _, k, d in events if k == "tour")},
            "per_day": dict(sorted(per_day.items())),
            "hours": hours,
            "per_user": sorted(per_user.values(), key=lambda u: -(u["last_active"] or 0)),
            "models": _count(f"{s['model']['providerID']}/{s['model']['modelID']}" for s in states),
        }

LOG_TEXT = [  # job log lines (English, for the detail page) -> the admin timeline's short Chinese labels
    ("done", "完成", "done"), ("waiting for review", "等待確認", "waiting"), ("waiting for the user to point", "等使用者指出清單", "waiting"),
    ("found ", "讀到條目", "stage"), ("citation order fixed", "引用順序修正", "stage"), ("already in the list", "新書目已在清單", "stage"),
    ("nothing to do", "沒有條目，直接完成", "done"), ("References section will be appended", "選擇文末新增", "stage"), ("list confirmed", "指出清單", "stage"),
]


def _log_events(s: dict) -> list[dict]:
    """A job's log lines carry only HH:MM:SS: rebuild full timestamps from the day the job started (rolling past midnight)."""
    base = time.localtime(s["started"])
    prev, out = s["started"], []
    for line in s.get("log", []):
        try:
            h, m, sec = map(int, line[:8].split(":"))
        except ValueError:
            continue
        t = time.mktime((base.tm_year, base.tm_mon, base.tm_mday, h, m, sec, 0, 0, -1))
        while t < prev - 1:
            t += 86400
        prev = t = max(t, prev)  # log times have no fraction: keep them after the start
        msg = line[9:]
        label, kind = next(((lb, k) for key, lb, k in LOG_TEXT if key in msg), (None, None))
        if label is None:
            label, kind = ("失敗：" + msg[:60], "failed") if s["status"] == "failed" and line == s["log"][-1] else (msg[:60], "stage")
        out.append({"t": t, "kind": kind, "user": s["user"], "text": f"{s['filename']}：{label}", "job": s["id"]})
    return out


API_TEXT = {"share": "建立分享", "research": "重新查詢", "choose": "選擇候選", "skip": "跳過條目", "continue": "繼續", "block": "指出清單", "split": "LLM 初排", "delete": "刪除工作",
            "result": "下載結果", "search": "單筆查詢", "reference": "單筆產生", "token": "產生 token", "me": "存設定"}
TOUR_TEXT = {"settings": "設定", "lookup": "單筆查詢", "work": "工作台", "done": "完成"}


def _event(t: float, user: str, via: str, kind: str, detail: str) -> dict:
    if via == "cron":
        text = f"每日戳 {detail}" if kind == "ping" else f"清除 {detail} 份超過 {RETAIN_DAYS} 天的文件"
        return {"t": t, "kind": "cron", "user": user, "text": text, "job": None}
    if kind == "tool":
        return {"t": t, "kind": "mcp", "user": user, "text": f"MCP {detail}", "job": None}
    if via == "public":
        return {"t": t, "kind": "web", "user": user, "text": "分享頁被看了" if kind == "share_view" else f"分享：{HIT_TEXT.get(detail, detail)}", "job": None}
    if kind == "tour":
        return {"t": t, "kind": "tour", "user": user, "text": f"教學到「{TOUR_TEXT.get(detail, detail)}」", "job": None}
    if kind in ("login", "register"):
        return {"t": t, "kind": "account", "user": user, "text": "登入" if kind == "login" else "註冊", "job": None}
    return {"t": t, "kind": "web", "user": user, "text": f"{'curl' if via == 'cli' else '網頁'}：{API_TEXT.get(detail, detail)}", "job": None}


def activity(hours: int) -> list[dict]:
    """Everything that happened in the last `hours`, oldest first: uploads, job log lines, single-reference results, sign-ups."""
    since = time.time() - hours * 3600
    with db.connect() as con:
        states = [json.loads(st) for (st,) in con.execute("SELECT state FROM jobs").fetchall()]
        refs = con.execute("SELECT user, created, query, check_ok FROM refs WHERE created >= ?", (since,)).fetchall()
        rows = con.execute("SELECT t, user, via, kind, detail FROM events WHERE t >= ?", (since,)).fetchall()
    ev = [{"t": s["started"], "kind": "upload", "user": s["user"], "text": f"上傳 {s['filename']}（{s['mode']}）", "job": s["id"]} for s in states]
    ev += [e for s in states for e in _log_events(s)]
    ev += [{"t": c, "kind": "single", "user": u, "text": f"單筆查詢{'' if ok else '（審查未過）'}：{q[:60]}", "job": None} for u, c, q, ok in refs]
    ev += [_event(t, u, via, kind, detail) for t, u, via, kind, detail in rows]
    return sorted((e for e in ev if e["t"] >= since), key=lambda e: e["t"])

def summary(s: dict) -> dict:
    return {k: s.get(k) for k in ("id", "user", "filename", "mode", "status", "stage", "percent", "started", "elapsed", "changed", "error")} | {"entries": len(s.get("items", [])), "ask": bool(s.get("ask")), "expired": bool(s.get("expired"))}


def _count(xs) -> dict:
    out = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out
