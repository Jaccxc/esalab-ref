import io

import pytest
import zipfile

from lxml import etree

from esalab import db, pipeline
from esalab.docx_track import NS, Doc, para_text
from tests.make_fixture import build


def _thesis_like(monkeypatch) -> bytes:
    """Body cites [2] before [1] (wrong order) and has a placeholder [+2]; list has 2 entries."""
    import tests.make_fixture as mf
    body = (
        '<w:p><w:r><w:t xml:space="preserve">Prior work [</w:t></w:r><w:r><w:t>2</w:t></w:r><w:r><w:t xml:space="preserve">] and [+2] matter; see also [1].</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>References</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>(請照IEEE format撰寫)</w:t></w:r></w:p>'
        '<w:p><w:r><w:t xml:space="preserve">[1]K.-Y. Ho, M. G. Blanchette, and C. M. Powers, “The influence of heel height,” </w:t></w:r>'
        '<w:r><w:rPr><w:i/></w:rPr><w:t xml:space="preserve">Gait &amp; Posture, </w:t></w:r><w:r><w:t>vol. 36, no. 2, pp. 271-275, Jun. 2012.</w:t></w:r></w:p>'
        '<w:p><w:r><w:t xml:space="preserve">[2]　M. Lan, J. Wang and L. Zhu, “Perception and Range Measurement,” in </w:t></w:r>'
        '<w:r><w:rPr><w:i/></w:rPr><w:t>IEEE Access</w:t></w:r><w:r><w:t>, vol. 11, pp. 126398-126408, 2023.</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Appendix text after the list.</w:t></w:r></w:p>'
    )
    doc = mf.DOC.split("<w:body>")[0] + "<w:body>" + body + "<w:sectPr/></w:body></w:document>"
    monkeypatch.setattr(mf, "DOC", doc)
    buf = io.BytesIO()
    build(buf)
    return buf.getvalue()


def test_entries_are_found_with_labels_and_italics(monkeypatch):
    doc = Doc(_thesis_like(monkeypatch))
    es = doc.entries()
    assert [e["label"] for e in es] == ["[1]", "[2]"]
    assert es[0]["text"].startswith("K.-Y. Ho") and "*Gait & Posture*, vol." in es[0]["text"]  # punctuation outside the italics (norm_marks)
    assert es[1]["text"].startswith("M. Lan")  # full-width space after the label is stripped
    assert doc.body_texts() == ["Prior work [2] and [+2] matter; see also [1]."]


class FakeAgent:
    base, model = "fake", {"providerID": "fake", "modelID": "fake"}
    sessions = 0

    def healthy(self):
        return True

    def ask(self, prompt, schema, title="x"):
        FakeAgent.sessions += 1
        if "reference" in schema["properties"] and "ok" in schema["properties"]:
            cand = prompt.split("CANDIDATE: ")[1].split("\n")[0]
            return {"ok": "and L. Zhu" not in cand, "problems": ["Oxford comma"], "reference": cand.replace(", J. Wang and", ", J. Wang, and")}
        if "confidence" in schema["properties"]:
            orig = prompt.split("ORIGINAL ENTRY (may be wrong or incomplete): ")[1].split("\n")[0]
            return {"type": "journal", "reference": orig.replace("*Gait & Posture, *vol.", "*Gait Posture*, vol.").replace("271-275", "271–275").replace("in *IEEE", "*IEEE"), "issues": [], "confidence": 0.9}
        return {"title": "x"}


def _fake_lookup(q, hint=None):
    exact = q in ("The influence of heel height", "Perception and Range Measurement", "Attention is all you need")
    return {"match": "exact" if exact else "fuzzy", "title": q, "source": "test", "candidates": [{"title": "Candidate A", "doi": "10/a"}]}


def test_smart_job_review_order_and_apply(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB", tmp_path / "t.db")
    monkeypatch.setattr(pipeline, "lookup", _fake_lookup)
    titles = ["The influence of heel height", "Attention is all you need", "Some unknown paper"]  # line 1 duplicates [1]
    job = pipeline.Job(_thesis_like(monkeypatch), "t.docx", "smart", titles, "tester", user="u", agent=FakeAgent())
    job._run()
    s = job.state
    assert s["status"] == "waiting" and s["stage"] == "review", s["error"]
    assert s["items"][2]["status"] == "duplicate" and s["items"][2]["duplicate_of"] == 1
    assert s["items"][4]["uncertain"] is True and s["items"][4]["meta"]["candidates"]
    job.choose(4, choice=0)  # the user picks candidate A for "Some unknown paper"
    assert job.state["items"][4]["meta"]["title"] == "Candidate A" and not job.state["items"][4]["uncertain"]
    found = job.research(4, "Attention is all you need")  # or re-searches with a better query: nothing changes until picked
    assert found["match"] == "exact" and job.state["items"][4]["meta"]["title"] == "Candidate A"
    job.choose(4, meta=found)
    assert job.state["items"][4]["meta"]["match"] == "exact" and job.state["items"][4]["meta"]["title"] == "Attention is all you need"
    job.skip([4])  # and finally decides to leave this entry alone

    FakeAgent.sessions = 0
    job.resume()
    for _ in range(200):
        if job.state["status"] in ("done", "failed"):
            break
        job.wait(job.version, timeout=0.1)
    assert s["status"] == "done", s["error"]
    assert FakeAgent.sessions == 6  # 3 entries x (format + check), each its own OpenCode session; the skipped one costs nothing
    assert "formatted" not in s["items"][4] and s["items"][4]["skip"] is True
    # body cites [2], [+2], [1]; +1 is a duplicate; +3 is uncited -> final [1]=old2, [2]=new2, [3]=old1, [4]=new3
    assert s["order"]["order"] == [2, "+2", 1, "+3"] and s["order"]["renumber"] == {1: 3, 2: 1}
    out = pipeline.Jobs().output(job.id, "u")
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(out)).read("word/document.xml"))
    paras = root.findall("w:body/w:p", NS)
    texts = [para_text(p) for p in paras]
    assert texts[0] == "Prior work [1] and [2] matter; see also [3]." and paras[0].xpath("./w:del/w:r/w:delText", namespaces=NS)
    assert texts[3].startswith("[1]M. Lan, J. Wang, and L. Zhu") and texts[4].startswith("[2]Attention is all you need")
    assert texts[5].startswith("[3]K.-Y. Ho") and texts[6].startswith("[4]Some unknown paper") and texts[7].startswith("Appendix")
    assert paras[3].xpath("./w:ins/w:r[w:rPr/w:i]/w:t/text()", namespaces=NS) == ["IEEE Access"]
    assert s["changed"] == 5 and s["body_changed"] == 1
    assert pipeline.Jobs().list("u")[0]["status"] == "done"


def test_fix_job_without_review_runs_straight_through(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB", tmp_path / "t.db")
    monkeypatch.setattr(pipeline, "lookup", _fake_lookup)
    job = pipeline.Job(_thesis_like(monkeypatch), "t.docx", "fix", [], "tester", user="u", review=False, agent=FakeAgent())
    job._run()
    assert job.state["status"] == "done", job.state["error"]
    assert job.state["order"]["placeholders"] == {} and job.state["order"]["renumber"] == {1: 2, 2: 1}


def test_waiting_job_is_rehydrated_after_restart(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB", tmp_path / "t.db")
    monkeypatch.setattr(pipeline, "lookup", _fake_lookup)
    job = pipeline.Job(_thesis_like(monkeypatch), "t.docx", "fix", [], "tester", user="u", agent=FakeAgent())
    job._run()
    assert job.state["status"] == "waiting"
    fresh = pipeline.Jobs()  # a new server process has no in-memory jobs
    again = fresh.get(job.id, "u")
    assert again is not None and again.state["status"] == "waiting" and again.docx == job.docx
    assert fresh.get(job.id, "someone-else") is None


def test_progress_percent_is_monotonic(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB", tmp_path / "t.db")
    job = pipeline.Job(_thesis_like(monkeypatch), "t.docx", "fix", [], "t", agent=FakeAgent())
    job._progress("lookup", 16, 17)
    assert 10 < job.state["percent"] < 20
    job._progress("format", 0, 17)
    assert job.state["percent"] == round(5 / 26 * 100, 1)


def test_delete_while_running_stops_the_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB", tmp_path / "t.db")
    monkeypatch.setattr(pipeline, "lookup", _fake_lookup)
    jobs = pipeline.Jobs()
    job = pipeline.Job(_thesis_like(monkeypatch), "t.docx", "fix", [], "tester", user="u", agent=FakeAgent(), review=False)
    jobs.jobs[job.id] = job
    job.state["status"] = "running"
    assert jobs.delete(job.id, "u") is True and job.stop.is_set()
    with pytest.raises(pipeline.Cancelled):
        job._emit()
    job._guarded([job._extract])  # the worker path swallows the cancel and writes nothing
    assert job.state["status"] == "running" and jobs.list("u") == []


def test_orphaned_running_jobs_fail_on_startup(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB", tmp_path / "t.db")
    jobs = pipeline.Jobs()
    job = pipeline.Job(_thesis_like(monkeypatch), "t.docx", "fix", [], "tester", user="u", agent=FakeAgent(), review=False)
    job.state["status"] = "running"
    job._emit()
    jobs.fail_orphans()
    assert jobs.list("u")[0]["status"] == "failed" and "重啟" in jobs.list("u")[0]["error"]
