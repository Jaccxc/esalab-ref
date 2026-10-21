import json
import io
import time

from fastapi.testclient import TestClient

from esalab import app as appmod, auth, db, pipeline
from tests.make_fixture import build


def _client(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB", tmp_path / "esalab.db")
    monkeypatch.setenv("JWT_SECRET", "test-secret-of-at-least-32-bytes-long")
    monkeypatch.setenv("OPENCODE_URL", "http://127.0.0.1:1")  # unreachable: jobs fail fast instead of calling an LLM
    monkeypatch.setenv("ADMIN_PASSWORD", "test-admin-pw")
    return TestClient(appmod.app)


def test_register_login_and_job_isolation(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    assert c.get("/api/jobs").status_code == 401  # every endpoint needs a token
    assert c.post("/api/register", json={"username": "ann", "password": "secret1"}).status_code == 201
    assert c.post("/api/register", json={"username": "ann", "password": "secret1"}).status_code == 409
    assert c.post("/api/login", json={"username": "ann", "password": "wrong"}).status_code == 401
    ann = {"Authorization": "Bearer " + c.post("/api/login", json={"username": "ann", "password": "secret1"}).json()["token"]}
    bob = {"Authorization": "Bearer " + c.post("/api/register", json={"username": "bob", "password": "secret2"}).json()["token"]}
    assert c.get("/api/me", headers=ann).json() == {"username": "ann", "admin": False, "author": "", "tour": None}

    buf = io.BytesIO()
    build(buf)
    jid = c.post("/api/jobs", files={"file": ("t.docx", buf.getvalue())}, data={"mode": "add", "titles": "x"}, headers=ann).json()["id"]
    assert c.get(f"/api/jobs/{jid}", headers=ann).json()["user"] == "ann"
    assert c.get(f"/api/jobs/{jid}", headers=bob).status_code == 404  # another user cannot see it
    assert c.get(f"/api/jobs/{jid}?token={ann['Authorization'][7:]}").status_code == 200  # query token for SSE/download
    assert [j["id"] for j in c.get("/api/jobs", headers=ann).json()] == [jid] and c.get("/api/jobs", headers=bob).json() == []
    assert c.delete(f"/api/jobs/{jid}", headers=bob).status_code == 404  # cannot delete someone else's


def test_admin_seed_stats_and_delete(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    appmod.auth.ensure_admin()  # seeded into the fresh test db
    assert c.get("/api/me", headers={"Authorization": "Bearer x"}).status_code == 401
    ann = {"Authorization": "Bearer " + c.post("/api/register", json={"username": "ann", "password": "secret1"}).json()["token"]}
    adm = {"Authorization": "Bearer " + c.post("/api/login", json={"username": "admin", "password": "test-admin-pw"}).json()["token"]}
    assert c.get("/api/me", headers=adm).json() == {"username": "admin", "admin": True, "author": "", "tour": None}
    monkeypatch.setattr(appmod.Agent, "healthy", lambda self: False)
    assert c.get("/api/health", headers=adm).json()["throttled"] == []
    assert c.get("/api/admin/stats", headers=ann).status_code == 403
    buf = io.BytesIO()
    build(buf)
    jid = c.post("/api/jobs", files={"file": ("t.docx", buf.getvalue())}, data={"mode": "add", "titles": "x"}, headers=ann).json()["id"]
    for _ in range(100):  # the worker fails fast (no opencode in tests); wait for a terminal status
        if c.get(f"/api/jobs/{jid}", headers=ann).json()["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    st = c.get("/api/admin/stats", headers=adm).json()
    assert st["users"] == 2 and st["jobs"]["failed"] + st["jobs"]["done"] == 1 and st["per_user"][0]["username"] == "ann"
    assert st["modes"]["add"] == 1 and sum(st["hours"]) == 1 and list(st["per_day"].values())[0]["jobs"] == 1 and st["per_user"][0]["refs"] == 0
    assert set(st) >= {"items", "types", "order", "asks", "blocks", "failures", "sources", "seconds_by_mode", "review", "cache"}
    assert [j["user"] for j in c.get("/api/admin/jobs", headers=adm).json()] == ["ann"]
    ev = c.get("/api/admin/activity?hours=1", headers=adm).json()
    assert [e["kind"] for e in ev][:2] == ["account", "account"] and any(e["kind"] == "upload" and e["user"] == "ann" for e in ev) and ev == sorted(ev, key=lambda e: e["t"])
    assert c.delete(f"/api/jobs/{jid}", headers=ann).status_code == 204 and c.get("/api/jobs", headers=ann).json() == []
    assert c.delete(f"/api/jobs/{jid}", headers=ann).status_code == 404 and c.get(f"/api/jobs/{jid}", headers=ann).status_code == 404
    st2 = c.get("/api/admin/stats", headers=adm).json()  # soft delete: the numbers survive, the file does not
    assert st2["jobs"] == st["jobs"] and st2["per_user"][0]["jobs"] == 1 and st2["cron"]["expired"] == 0
    with db.connect() as con:
        assert con.execute("SELECT input, output, deleted IS NOT NULL FROM jobs WHERE id=?", (jid,)).fetchone() == (None, None, 1)
    ev = c.get("/api/admin/activity?hours=1", headers=adm).json()
    assert ev[-1]["kind"] == "web" and ev[-1]["text"] == "網頁：刪除工作" and c.get("/api/admin/stats", headers=adm).json()["api"]["via"] == {"web": 1}


def test_search_and_single_reference(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    appmod.auth.ensure_admin()
    monkeypatch.setattr(appmod, "lookup", lambda q, hint=None: {"title": q, "match": "exact", "candidates": []})
    monkeypatch.setattr(appmod, "single_reference", lambda q, meta=None: iter(["format", "check", {"meta": meta or {"title": q}, "type": "journal", "issues": [], "formatted": "X", "check": {"ok": True, "problems": []}, "reference": "A. B, “" + q + ",” 2020."}]))
    ann = {"Authorization": "Bearer " + c.post("/api/register", json={"username": "ann", "password": "secret1"}).json()["token"]}
    assert c.post("/api/search", json={"query": "Attention"}).status_code == 401
    assert c.post("/api/search", json={"query": "Attention"}, headers=ann).json()["match"] == "exact"
    rid = c.post("/api/reference", json={"query": "Attention"}, headers=ann).json()["id"]
    for _ in range(50):
        st = c.get(f"/api/reference/{rid}", headers=ann).json()
        if st["stage"] == "done":
            break
        time.sleep(0.05)
    r = st["result"]
    assert r["reference"].startswith("A. B") and r["id"] == rid
    assert c.get(f"/api/reference/{rid}").status_code == 401 and c.get("/api/reference/nope", headers=ann).status_code == 404
    # a task cut off mid-run is restarted on startup
    with db.connect() as con:
        con.execute("INSERT INTO single_tasks VALUES ('cut1','ann',0,'Attention',NULL,'format',NULL,NULL)")
    appmod.resume_single_tasks()
    for _ in range(50):
        if c.get("/api/reference/cut1", headers=ann).json()["stage"] == "done":
            break
        time.sleep(0.05)
    assert c.get("/api/reference/cut1", headers=ann).json()["result"]["id"] == "cut1"
    hist = c.get("/api/references", headers=ann).json()
    assert len(hist) == 2 and {h["id"] for h in hist} == {rid, "cut1"} and hist[0]["check"]["ok"] is True
    adm = {"Authorization": "Bearer " + c.post("/api/login", json={"username": "admin", "password": "test-admin-pw"}).json()["token"]}
    sr = c.get("/api/admin/stats", headers=adm).json()["single_refs"]
    assert (sr["total"], sr["check_ok"], sr["tasks"]) == (2, 2, {"done": 2}) and sum(sr["types"].values()) == 2


def test_prefs_and_default_author(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    ann = {"Authorization": "Bearer " + c.post("/api/register", json={"username": "ann", "password": "secret1"}).json()["token"]}
    assert c.get("/api/me", headers=ann).json()["author"] == ""
    assert c.put("/api/me", json={"author": " Ann Lee "}, headers=ann).json()["author"] == "Ann Lee"
    assert c.get("/api/me", headers=ann).json()["author"] == "Ann Lee"
    buf = io.BytesIO(); build(buf)
    jid = c.post("/api/jobs", files={"file": ("t.docx", buf.getvalue())}, data={"mode": "add", "titles": "x", "author": " "}, headers=ann).json()["id"]
    assert c.get(f"/api/jobs/{jid}", headers=ann).json()["author"] == "ESALab-RefBot"


def test_job_pauses_for_review_by_default(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    monkeypatch.setattr(pipeline, "lookup", lambda q, hint=None: {"title": q, "match": "exact", "candidates": []})
    monkeypatch.setattr(pipeline.Agent, "healthy", lambda self: True)
    ann = {"Authorization": "Bearer " + c.post("/api/register", json={"username": "ann", "password": "secret1"}).json()["token"]}
    buf = io.BytesIO()
    build(buf)
    jid = c.post("/api/jobs", files={"file": ("t.docx", buf.getvalue())}, data={"mode": "add", "titles": "x"}, headers=ann).json()["id"]
    for _ in range(100):
        s = c.get(f"/api/jobs/{jid}", headers=ann).json()
        if s["status"] in ("waiting", "done", "failed"):
            break
        time.sleep(0.05)
    assert s["status"] == "waiting" and s["review"] is True
    assert c.post(f"/api/jobs/{jid}/research", json={"index": 0, "query": "y"}, headers=ann).json()["title"] == "y"
    assert c.get(f"/api/jobs/{jid}", headers=ann).json()["items"][0]["meta"]["title"] == "x"  # research only proposes
    assert c.post(f"/api/jobs/{jid}/choose", json={"index": 0, "meta": {"title": "y", "match": "fuzzy", "error": "e"}}, headers=ann).json()["meta"] == {"title": "y", "match": "exact", "candidates": []}
    assert c.post(f"/api/jobs/{jid}/skip", json={"indexes": [0]}, headers=ann).json() == {"ok": True}
    assert c.post(f"/api/jobs/{jid}/skip", json={"indexes": [9]}, headers=ann).status_code == 400
    assert c.get(f"/api/jobs/{jid}", headers=ann).json()["items"][0]["skip"] is True
    assert c.post(f"/api/jobs/{jid}/choose", json={"index": 0, "keep": True}, headers=ann).json()["meta"]["kept"] is True
    assert c.post(f"/api/jobs/{jid}/choose", json={"index": 0, "choice": 5}, headers=ann).status_code == 400
    assert c.post(f"/api/jobs/{jid}/continue", headers=ann).status_code == 202
    assert c.post(f"/api/jobs/{jid}/continue", headers=ann).status_code == 409  # no longer waiting


def test_result_name_is_dated_and_numbered():
    t = 1792521368  # 2026-10-21 in Taiwan
    done = lambda st, status="done": {"filename": "thesis.docx", "status": status, "started": st}  # noqa: E731
    assert appmod.result_name(done(t), [done(t)]) == "thesis_esaref_261021.docx"
    jobs = [done(t + 20), done(t + 10), done(t + 5, "failed"), done(t), done(t - 86400)]  # newest first, like JOBS.list
    assert appmod.result_name(done(t + 20), jobs) == "thesis_esaref_261021_2.docx"
    assert appmod.result_name(done(t + 10), jobs) == "thesis_esaref_261021_1.docx"
    assert appmod.result_name(done(t - 86400), jobs) == "thesis_esaref_261020.docx"


def test_tour_stage_is_per_user_and_admin_can_reset(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)  # no lifespan here: the MCP session manager can only be started once per process
    if True:
        ann = {"Authorization": "Bearer " + c.post("/api/register", json={"username": "ann", "password": "secret1"}).json()["token"]}
        assert c.get("/api/me", headers=ann).json()["tour"] is None
        assert c.put("/api/me/tour", json={"stage": "nope"}, headers=ann).status_code == 400
        assert c.put("/api/me/tour", json={"stage": "lookup"}, headers=ann).json()["tour"] == "lookup"
        saved = c.put("/api/me", json={"author": "Ann"}, headers=ann).json()
        assert (saved["author"], saved["tour"]) == ("Ann", "lookup")
        assert c.put("/api/admin/users/ann/tour", json={"stage": "done"}, headers=ann).status_code == 403
        monkeypatch.setattr(auth, "ADMINS", {"ann"})
        assert c.put("/api/admin/users/ann/tour", json={"stage": "settings"}, headers=ann).json()["tour"] == "settings"
        assert c.get("/api/me", headers=ann).json()["tour"] == "settings"
        assert c.get("/api/admin/stats", headers=ann).json()["per_user"][0]["tour"] == "settings"


def test_cron_purge_and_ping(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    appmod.auth.ensure_admin()
    ann = {"Authorization": "Bearer " + c.post("/api/register", json={"username": "ann", "password": "secret1"}).json()["token"]}
    adm = {"Authorization": "Bearer " + c.post("/api/login", json={"username": "admin", "password": "test-admin-pw"}).json()["token"]}
    buf = io.BytesIO()
    build(buf)
    jid = c.post("/api/jobs", files={"file": ("t.docx", buf.getvalue())}, data={"mode": "add", "titles": "x"}, headers=ann).json()["id"]
    for _ in range(100):
        if c.get(f"/api/jobs/{jid}", headers=ann).json()["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    with db.connect() as con:  # pretend the upload happened 31 days ago; a job still waiting for the user is just as old but kept
        con.execute("UPDATE jobs SET started=? WHERE id=?", (time.time() - 31 * 86400, jid))
        w = json.loads(con.execute("SELECT state FROM jobs WHERE id=?", (jid,)).fetchone()[0]) | {"id": "w1", "status": "waiting"}
        con.execute("INSERT INTO jobs (id, user, started, state, input) VALUES ('w1','ann',?,?,?)", (time.time() - 40 * 86400, json.dumps(w), b"docx"))
    monkeypatch.setattr(pipeline, "_openalex", lambda t: [{"title": t}])
    s2 = iter([[], [{"title": "x"}]])  # first call throttled, the retry answers
    monkeypatch.setattr(pipeline, "_semanticscholar", lambda t: next(s2))
    appmod.JOBS.cron()
    appmod.JOBS.cron()  # second tick within a day: purge finds nothing, no second ping
    with db.connect() as con:
        assert con.execute("SELECT input, output FROM jobs WHERE id=?", (jid,)).fetchone() == (None, None)
        assert con.execute("SELECT input FROM jobs WHERE id='w1'").fetchone() == (b"docx",)
        assert con.execute("SELECT COUNT(*) FROM events WHERE kind='ping'").fetchone()[0] == 2
    j = c.get("/api/jobs", headers=ann).json()[0]
    assert j["expired"] and j["status"] == "failed"
    assert c.get(f"/api/jobs/{jid}/result.docx", headers=ann).status_code == 404
    cron = c.get("/api/admin/stats", headers=adm).json()["cron"]
    assert cron["ping"]["apis"] == {"openalex": "ok", "semanticscholar": "ok"} and cron["purge"]["n"] == 1 and cron["expired"] == 1
    texts = [e["text"] for e in c.get("/api/admin/activity?hours=1", headers=adm).json() if e["kind"] == "cron"]
    assert texts == ["清除 1 份超過 30 天的文件", "每日戳 openalex ok", "每日戳 semanticscholar ok"]


def test_share(monkeypatch, tmp_path):
    c = _client(monkeypatch, tmp_path)
    appmod.auth.ensure_admin()
    ann = {"Authorization": "Bearer " + c.post("/api/register", json={"username": "ann", "password": "secret1"}).json()["token"]}
    adm = {"Authorization": "Bearer " + c.post("/api/login", json={"username": "admin", "password": "test-admin-pw"}).json()["token"]}
    buf = io.BytesIO()
    build(buf)
    jid = c.post("/api/jobs", files={"file": ("t.docx", buf.getvalue())}, data={"mode": "add", "titles": "x"}, headers=ann).json()["id"]
    for _ in range(100):
        if c.get(f"/api/jobs/{jid}", headers=ann).json()["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert c.post(f"/api/jobs/{jid}/share", headers=ann).status_code == 404  # failed job (no opencode): nothing to share
    with db.connect() as con:  # pretend it finished
        s = json.loads(con.execute("SELECT state FROM jobs WHERE id=?", (jid,)).fetchone()[0])
        s.update(status="done", changed=2, order={"ok": False, "renumber": {"3": 1}, "placeholders": {}, "uncited": [2], "unknown": []})
        con.execute("UPDATE jobs SET state=? WHERE id=?", (json.dumps(s), jid))
    appmod.JOBS.jobs.pop(jid)  # the live copy would shadow the edited row
    tok = c.post(f"/api/jobs/{jid}/share", headers=ann).json()["token"]
    assert c.post(f"/api/jobs/{jid}/share", headers=ann).json()["token"] == tok  # one token per job
    assert c.post(f"/api/jobs/{jid}/share", headers=adm).status_code == 404  # not the owner
    sh = c.get(f"/api/share/{tok}").json()  # no login needed
    assert sh["user"] == "ann" and sh["job"]["filename"] == "t.docx" and sh["facts"]["renumbered"] == 1 and sh["facts"]["uncited"] == 1
    assert "quips" not in sh
    assert c.get("/api/share/nope").status_code == 404
    png = c.get(f"/api/share/{tok}/card.png")
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"
    html = c.get(f"/s/{tok}", headers={"host": "x.test", "x-forwarded-proto": "https"}).text
    assert f'og:image" content="https://x.test/api/share/{tok}/card.png"' in html and f"/#/s/{tok}" in html
    assert c.post(f"/api/share/{tok}/hit", json={"via": "copy"}).status_code == 204
    assert c.post(f"/api/share/{tok}/hit", json={"via": "telegram"}).status_code == 404
    st = c.get("/api/admin/stats", headers=adm).json()
    assert st["shares"] == {"total": 1, "views": 1, "hits": {"複製連結": 1}} and "public" not in st["api"]["via"]
    texts = [e["text"] for e in c.get("/api/admin/activity?hours=1", headers=adm).json() if e["user"] == "ann" and e["kind"] == "web"]
    assert texts == ["網頁：建立分享"] * 2 + ["分享頁被看了", "分享：複製連結"]  # the second share POST is idempotent but still logged
    with db.connect() as con:  # the card is purged with the docx, and drawn again on demand
        con.execute("UPDATE jobs SET started=? WHERE id=?", (time.time() - 31 * 86400, jid))
        con.execute("UPDATE shares SET png_at=? WHERE token=?", (time.time() - 31 * 86400, tok))
    appmod.JOBS.purge()
    with db.connect() as con:
        assert con.execute("SELECT png FROM shares WHERE token=?", (tok,)).fetchone() == (None,)
    assert c.get(f"/api/share/{tok}/card.png").status_code == 200 and c.get(f"/api/share/{tok}").json()["job"]["expired"]
    assert c.delete(f"/api/jobs/{jid}", headers=ann).status_code in (200, 204)
    assert c.get(f"/api/share/{tok}").status_code == 404
