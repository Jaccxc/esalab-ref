import io
import json
import time

from fastapi.testclient import TestClient

from esalab import app as appmod, db, pipeline
from tests.make_fixture import build

H = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB", tmp_path / "t.db")
    monkeypatch.setenv("ESALAB_CRON", "0")  # the lifespan would otherwise ping the real APIs
    monkeypatch.setattr(pipeline, "lookup", lambda q, hint=None: {"title": q, "match": "exact", "candidates": []})
    monkeypatch.setattr(pipeline.Agent, "healthy", lambda self: True)
    return TestClient(appmod.app)


def _call(c, tool, args, headers):
    r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}, headers=H | headers)
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert not res.get("isError"), res
    sc = res.get("structuredContent")
    if sc is None:  # dict results come back as JSON text only
        return json.loads(res["content"][0]["text"])
    return sc["result"] if set(sc) == {"result"} else sc  # lists are wrapped in {"result": [...]}


def test_mcp_needs_a_token_and_drives_a_job(monkeypatch, tmp_path):
    with _client(monkeypatch, tmp_path) as c:
        assert c.post("/mcp", json={}, headers=H).status_code == 401
        ann = {"Authorization": "Bearer " + c.post("/api/register", json={"username": "ann", "password": "secret1"}).json()["token"]}
        long = {"Authorization": "Bearer " + c.post("/api/token", headers=ann).json()["token"]}
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 0, "method": "tools/list"}, headers=H | long)
        names = {t["name"] for t in r.json()["result"]["tools"]}
        assert {"how_to_upload", "review_job", "choose", "skip", "continue_job", "result_link", "lookup_reference"} <= names
        assert "esalab://rules" in {x["uri"] for x in c.post("/mcp", json={"jsonrpc": "2.0", "id": 0, "method": "resources/list"}, headers=H | long).json()["result"]["resources"]}
        how = _call(c, "how_to_upload", {}, long | {"X-Forwarded-Proto": "https", "Host": "x.ngrok.app"})
        assert how["endpoint"] == "https://x.ngrok.app/api/jobs" and long["Authorization"][7:] in how["bash"]
        buf = io.BytesIO()
        build(buf)
        jid = c.post("/api/jobs", files={"file": ("t.docx", buf.getvalue())}, data={"mode": "add", "titles": "x"}, headers=long).json()["id"]
        for _ in range(300):
            g = _call(c, "get_job", {"job_id": jid}, long)
            if g["status"] in ("waiting", "done", "failed"):
                break
            time.sleep(0.1)
        assert g["status"] == "waiting", g
        assert _call(c, "list_jobs", {}, long)[0]["id"] == jid
        rows = _call(c, "review_job", {"job_id": jid, "all_entries": True}, long)
        assert rows and rows[0]["label"] and rows[0]["match"] == "exact"
        found = _call(c, "research", {"job_id": jid, "index": 0, "query": "y"}, long)
        assert found["title"] == "y" and _call(c, "choose", {"job_id": jid, "index": 0, "meta": found}, long)["title"] == "y"
        assert _call(c, "skip", {"job_id": jid, "indexes": [0]}, long) == {"skipped": 1}
        assert _call(c, "continue_job", {"job_id": jid}, long)["status"] == "running"
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "result_link", "arguments": {"job_id": "nope"}}}, headers=H | long)
        assert r.json()["result"]["isError"] is True
