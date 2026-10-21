"""MCP endpoint (Streamable HTTP at /mcp) for agent clients: the same actions as the web UI, under the caller's
Bearer token. Uploading the .docx stays on POST /api/jobs (curl); everything after that is a tool here."""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import anyio
from fastapi import HTTPException
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError  # a ValueError would reach the client as a bare 'Error executing tool'
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from esalab import auth, db
from esalab.share import public_base
from esalab.agent import RULES
from esalab.lookup import lookup
from esalab.pipeline import Jobs, summary

server = MCPServer(
    "esalab-ref",
    instructions="ESA Lab (NTPU CSIE) thesis reference tool. Workflow: upload the .docx with the curl command from "
                 "how_to_upload (POST /api/jobs) -> get_job until status is 'waiting' -> review_job, then research / "
                 "choose / skip per entry -> continue_job -> get_job until 'done' -> result_link. Single entries: "
                 "lookup_reference (metadata only) or format_reference (IEEE entry via LLM). Read esalab://rules for the style.",
)


def _bearer(ctx: Context) -> str:
    a = (ctx.headers or {}).get("authorization", "")
    return a[7:] if a.lower().startswith("bearer ") else ""


def _base(ctx: Context) -> str:
    return public_base(ctx.headers or {})


def _compact(m: dict | None) -> dict | None:
    return m and {k: m.get(k) for k in ("match", "title", "year", "venue", "doi", "source", "error") if m.get(k) is not None}


def build(jobs: Jobs, start_single: Callable[[str, str, dict | None], str]):
    """Register the tools (closing over the app's job registry) and return the authenticated ASGI app for /mcp."""

    def user(ctx: Context) -> str:
        return auth.user_of(_bearer(ctx))

    def log(ctx: Context, tool: str) -> str:
        u = user(ctx)
        db.event(u, "mcp", "tool", tool)
        return u

    def waiting(job_id: str, u: str):
        job = jobs.get(job_id, u)
        if not job or job.state["status"] != "waiting":
            raise ToolError("這筆工作不在等待確認的狀態")
        return job

    def state(job_id: str, u: str) -> dict:
        s = jobs.state(job_id, u)
        if not s:
            raise ToolError("沒有這筆工作")
        return s

    @server.tool()
    async def lookup_reference(query: str, ctx: Context) -> dict:
        """Find the bibliographic record (Crossref / OpenAlex / Semantic Scholar) for a title, DOI, arXiv id or URL. No LLM, seconds."""
        log(ctx, "lookup_reference")
        return await anyio.to_thread.run_sync(lookup, query)

    @server.tool()
    async def format_reference(query: str, ctx: Context, wait_seconds: int = 120) -> dict:
        """Produce one ESA Lab IEEE-style reference for a title/DOI/URL (lookup, LLM format, LLM check: 1-3 minutes).
        Returns the result, or {id, stage} to poll with get_task if it is not done within wait_seconds."""
        log(ctx, "format_reference")
        rid = start_single(user(ctx), query, None)
        for _ in range(max(1, wait_seconds // 2)):
            await anyio.sleep(2)
            t = await get_task(rid, ctx)
            if t["stage"] in ("done", "failed"):
                return t
        return {"id": rid, "stage": t["stage"], "hint": "still running; call get_task(id) later"}

    @server.tool()
    async def get_task(task_id: str, ctx: Context) -> dict:
        """Status of a format_reference task: stage lookup|format|check|done|failed, result when done."""
        with db.connect() as con:
            row = con.execute("SELECT stage, result, error FROM single_tasks WHERE id=? AND user=?", (task_id, user(ctx))).fetchone()
        if not row:
            raise ToolError("沒有這個任務")
        return {"id": task_id, "stage": row[0], "result": json.loads(row[1]) if row[1] else None, "error": row[2]}

    @server.tool()
    async def how_to_upload(ctx: Context) -> dict:
        """How to start a job: the curl command that uploads a .docx to POST /api/jobs and returns {"id"}. Run it in a shell."""
        log(ctx, "how_to_upload")
        base, tok = _base(ctx), _bearer(ctx)
        return {
            "endpoint": f"{base}/api/jobs",
            "fields": {"file": "the .docx", "mode": "smart (default) | fix | add", "titles": "new entries, one per line (optional)",
                       "author": "name for the Word tracked changes (optional)", "review": "true (default: pause for review) | false"},
            "bash": f'curl -sS -X POST "{base}/api/jobs" -H "Authorization: Bearer {tok}" -F "file=@thesis.docx" -F "mode=smart" -F "titles=First new title\nSecond new title"',
            "powershell": f'curl.exe -sS -X POST "{base}/api/jobs" -H "Authorization: Bearer {tok}" -F "file=@thesis.docx" -F "mode=smart" -F "titles=First new title`nSecond new title"',
            "then": "poll get_job(id) every 10-30 s; status 'waiting' means review_job is needed, 'done' means result_link",
        }

    @server.tool()
    async def list_jobs(ctx: Context) -> list[dict]:
        """Your jobs, newest first: id, filename, mode, status (queued|running|waiting|done|failed), stage, percent,
        ask (true = waiting for reference_block, not for review)."""
        return jobs.list(user(ctx))

    @server.tool()
    async def get_job(job_id: str, ctx: Context) -> dict:
        """Progress of one job plus its log and, after the order step, the citation-order plan (renumber / placeholders / uncited / unknown)."""
        s = state(job_id, user(ctx))
        return summary(s) | {"error": s.get("error"), "eta_seconds": s.get("eta_seconds"), "order": s.get("order"), "log": s.get("log", [])[-15:],
                             "uncertain": sum(1 for it in s["items"] if it.get("uncertain")), "skipped": sum(1 for it in s["items"] if it.get("skip"))}

    @server.tool()
    async def reference_block(job_id: str, ctx: Context) -> dict:
        """When get_job shows ask=true the job stopped at 'extract': no `[n]` entries were readable under a References
        heading. Returns why (reason: no_heading | empty | no_labels | blob) and the candidate paragraphs after the heading
        (index, text, numbered, likely). Answer with set_reference_block: pass paras=[indexes that are entries] to use their
        text as-is, or entries=[one string per entry] (with paras = the paragraphs they replace, e.g. the single blob
        paragraph) when the text needs re-splitting; split_reference_text does that split for you. The job then
        renumbers them [1]..[n] in order and continues to lookup."""
        log(ctx, "reference_block")
        s = state(job_id, user(ctx))
        if not s.get("ask"):
            raise ToolError("這筆工作沒有在等參考文獻區塊的回答")
        a = s["ask"]
        return a | {"mode": s["mode"], "titles_given": sum(1 for t in s.get("titles", []) if t.strip()),
                    "hint": "entries must be one paragraph each starting with [n]; confirm the paragraphs with set_reference_block"}

    @server.tool()
    async def split_reference_text(job_id: str, text: str, ctx: Context) -> dict:
        """LLM pre-arrangement of a pasted list: one entry per item, text untouched. Returns {entries}; pass them to
        set_reference_block after checking nothing was dropped."""
        log(ctx, "split_reference_text")
        return {"entries": await anyio.to_thread.run_sync(waiting(job_id, user(ctx)).split, text)}

    @server.tool()
    async def set_reference_block(job_id: str, ctx: Context, paras: list[int] | None = None, entries: list[str] | None = None,
                                  heading: int | None = None, append: bool = False) -> dict:
        """Answer reference_block. paras: paragraph indexes that are entries (their text is used). entries: the entry texts
        when re-split (entry k replaces paragraph paras[k], extra entries are appended after the last). heading defaults to
        the one reference_block found. append=True: the document has no reference list at all; a 'References' section with
        the job's given titles is added at the end (with no titles the job just finishes with nothing to do)."""
        log(ctx, "set_reference_block")
        job = waiting(job_id, user(ctx))
        a = job.state.get("ask") or {}
        try:
            job.set_block(a.get("heading") if heading is None else heading, paras or [], entries, append)
        except ValueError as e:
            raise ToolError(str(e))
        return {"id": job_id, "status": "running"}

    @server.tool()
    async def review_job(job_id: str, ctx: Context, all_entries: bool = False) -> list[dict]:
        """Entries that need a human/agent decision while the job is 'waiting': fuzzy matches (chosen paper + candidates)
        and none (nothing found). all_entries=True lists every entry. Use research / choose / skip, then continue_job.
        If get_job shows ask=true the job is waiting for reference_block instead."""
        log(ctx, "review_job")
        s = state(job_id, user(ctx))
        if s.get("ask"):
            raise ToolError("這筆工作停在讀取條目：先用 reference_block / set_reference_block 指出參考文獻在哪")
        out = []
        for i, it in enumerate(s["items"]):
            if it["status"] == "duplicate" or not (all_entries or it.get("uncertain")):
                continue
            m = it.get("meta") or {}
            out.append({"index": i, "label": f"[{it['number']}]" if it["kind"] == "fix" else f"+{it['line']}", "original": it["original"],
                        "match": m.get("match"), "chosen": _compact(m), "candidates": [_compact(c) for c in m.get("candidates", [])],
                        "skip": bool(it.get("skip"))})
        return out

    @server.tool()
    async def research(job_id: str, index: int, query: str, ctx: Context) -> dict:
        """Look an entry up again with a better query (DOI, URL or full title). Nothing changes until you pass the
        returned record to choose(meta=...); its 'candidates' can be passed too."""
        log(ctx, "research")
        return await anyio.to_thread.run_sync(waiting(job_id, user(ctx)).research, index, query)

    @server.tool()
    async def choose(job_id: str, index: int, ctx: Context, meta: dict[str, Any] | None = None, candidate: int | None = None) -> dict:
        """Settle an entry: meta = a record from research, or candidate = position in the entry's candidates list."""
        log(ctx, "choose")
        job = waiting(job_id, user(ctx))
        if meta is None and candidate is None:
            raise ToolError("給 meta 或 candidate 其中一個")
        try:
            return _compact(job.choose(index, candidate, False, meta)["meta"])
        except (IndexError, TypeError):
            raise ToolError("沒有這個候選")

    @server.tool()
    async def skip(job_id: str, indexes: list[int], ctx: Context, skip: bool = True) -> dict:
        """Leave these entries exactly as written (only renumbered): no LLM formatting. skip=False undoes it."""
        log(ctx, "skip")
        job = waiting(job_id, user(ctx))
        if any(not 0 <= i < len(job.state["items"]) for i in indexes):
            raise ToolError("index 超出範圍")
        job.skip(indexes, skip)
        return {"skipped": sum(1 for it in job.state["items"] if it.get("skip"))}

    @server.tool()
    async def continue_job(job_id: str, ctx: Context) -> dict:
        """Finish the review: order check, LLM formatting, LLM check, write tracked changes. Poll get_job until 'done'."""
        log(ctx, "continue_job")
        job = waiting(job_id, user(ctx))
        if job.state.get("ask"):
            raise ToolError("這筆工作停在讀取條目：先用 reference_block / set_reference_block 指出參考文獻在哪")
        job.resume()
        return {"id": job_id, "status": "running"}

    @server.tool()
    async def job_entries(job_id: str, ctx: Context) -> list[dict]:
        """Final entries of a finished job: number, text (as written back), changed, LLM notes and check problems."""
        s = state(job_id, user(ctx))
        return [{"number": it.get("number_final"), "text": it.get("final") or it["original"], "changed": it.get("changed"),
                 "skip": bool(it.get("skip")), "issues": it.get("issues", []), "problems": (it.get("check") or {}).get("problems", [])}
                for it in sorted(s["items"], key=lambda it: it.get("number_final") or 0) if it["status"] != "duplicate"]

    @server.tool()
    async def result_link(job_id: str, ctx: Context) -> dict:
        """Download link (tokenised) for the revised .docx of a finished job, and a curl command that saves it."""
        log(ctx, "result_link")
        s = state(job_id, user(ctx))
        if s["status"] != "done":
            raise ToolError("這筆工作還沒完成")
        url = f"{_base(ctx)}/api/jobs/{job_id}/result.docx?token={_bearer(ctx)}"
        return {"url": url, "bash": f'curl -sS -OJ "{url}"', "note": "the server names the file <origin>_esaref_<yymmdd>.docx"}

    @server.resource("esalab://rules", name="ESA Lab IEEE reference rules", mime_type="text/markdown")
    def rules() -> str:
        return RULES

    inner = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                       transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

    return _Guarded(inner)


class _Guarded:
    """ASGI wrapper (a class, so Starlette's Route treats it as an app, not a request handler): 401 before the MCP
    layer sees anything; the tools re-read the token themselves."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            try:
                auth.current_user(Request(scope))
            except HTTPException:
                await JSONResponse({"error": "Authorization: Bearer <token> required; get one on the MCP page"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)
