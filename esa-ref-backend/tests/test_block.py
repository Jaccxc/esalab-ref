"""The reference-block question: Word-numbered lists read directly; unreadable lists stop the job until the user points at them."""
import io
import zipfile

from lxml import etree

from esalab import db, pipeline
from esalab.docx_track import NS, Doc, para_text
from tests.make_fixture import build
from tests.test_pipeline import FakeAgent, _fake_lookup

NUMBERING = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:numFmt w:val="decimal"/><w:lvlText w:val="[%1]"/></w:lvl></w:abstractNum>
<w:num w:numId="2"><w:abstractNumId w:val="0"/></w:num></w:numbering>"""
NUM = '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr></w:pPr>'


def _docx(monkeypatch, body: str, numbering: bool = False) -> bytes:
    import tests.make_fixture as mf
    doc = mf.DOC.split("<w:body>")[0] + "<w:body>" + body + "<w:sectPr/></w:body></w:document>"
    monkeypatch.setattr(mf, "DOC", doc)
    buf = io.BytesIO()
    build(buf)
    if numbering:
        out = io.BytesIO()
        with zipfile.ZipFile(buf) as zin, zipfile.ZipFile(out, "w") as zout:
            for info in zin.infolist():
                zout.writestr(info, zin.read(info.filename))
            zout.writestr("word/numbering.xml", NUMBERING)
        return out.getvalue()
    return buf.getvalue()


BODY = '<w:p><w:r><w:t>See [2] and [1].</w:t></w:r></w:p><w:p><w:r><w:t>References</w:t></w:r></w:p>'
P1 = '<w:r><w:t>A. One, “First paper,” vol. 1, 2020.</w:t></w:r>'
P2 = '<w:r><w:t>B. Two, “Second paper,” vol. 2, 2021.</w:t></w:r>'


def _paras(out: bytes):
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(out)).read("word/document.xml"))
    return root.findall("w:body/w:p", NS)


def test_word_numbered_list_is_read_and_written_back_with_typed_labels():
    import pytest
    mp = pytest.MonkeyPatch()
    d = _docx(mp, BODY + f"<w:p>{NUM}{P1}</w:p><w:p>{NUM}{P2}</w:p>", numbering=True)
    mp.undo()
    doc = Doc(d)
    assert [e["label"] for e in doc.entries()] == ["[1]", "[2]"] and doc.relabel
    out, _ = doc.apply({2: "[1]\tA. One, fixed."}, [], "t")
    ps = _paras(out)
    assert para_text(ps[2]).startswith("[1]") and ps[2].find("w:pPr/w:numPr", NS) is None
    assert ps[3].find("w:pPr/w:numPr", NS) is None  # the untouched neighbour loses its auto number too (the job rewrites it)


def test_suggest_and_confirmed_block(monkeypatch):
    d = _docx(monkeypatch, BODY + f"<w:p>{P1}</w:p><w:p>{P2}</w:p><w:p><w:r><w:t>not a reference</w:t></w:r></w:p>")
    doc = Doc(d)
    assert doc.entries() == []
    s = doc.suggest()
    assert s["reason"] == "no_labels" and s["heading"] == 1 and [c["index"] for c in s["candidates"]] == [2, 3, 4]
    assert [c["likely"] for c in s["candidates"]] == [True, True, False]
    doc = Doc(d, {"heading": 1, "paras": [2, 3]})
    assert [(e["index"], e["label"], e["text"][:6]) for e in doc.entries()] == [(2, "[1]", "A. One"), (3, "[2]", "B. Two")]
    assert doc.body_texts() == ["See [2] and [1]."]


def test_blob_paragraph_is_split_into_entries(monkeypatch):
    blob = '<w:p><w:r><w:t>1. A. One, “First paper,” vol. 1, 2020.</w:t><w:br/><w:t>2. B. Two, “Second paper,” vol. 2, 2021.</w:t></w:r></w:p>'
    d = _docx(monkeypatch, BODY + blob)
    s = Doc(d).suggest()
    assert s["reason"] == "blob" and s["candidates"][0]["text"].count("\n") == 1 and s["candidates"][0]["numbered"] == "1."
    prose = "<w:p><w:r><w:t>" + "This is not a reference list, just a long note. " * 8 + "</w:t></w:r></w:p>"
    assert Doc(_docx(monkeypatch, BODY + prose)).suggest()["reason"] == "no_labels"  # long but no year/vol./doi: ask, don't split
    doc = Doc(d, {"heading": 1, "paras": [2], "entries": s["candidates"][0]["text"].split("\n")})
    es = doc.entries()
    assert [(e["index"], e["text"][:6]) for e in es] == [(2, "A. One"), (None, "B. Two")]
    out, _ = doc.apply({2: "[1]\tA. One"}, ["[2]\tB. Two"], "t")
    assert [para_text(p) for p in _paras(out)[2:4]] == ["[1]A. One", "[2]B. Two"]  # the tab is a <w:tab/>, invisible to para_text


def test_job_waits_for_the_block_then_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB", tmp_path / "t.db")
    monkeypatch.setattr(pipeline, "lookup", _fake_lookup)
    blob = '<w:p><w:r><w:t>A. One, “First paper,” vol. 1, 2020.</w:t><w:br/><w:t>B. Two, “Second paper,” vol. 2, 2021.</w:t></w:r></w:p>'
    job = pipeline.Job(_docx(monkeypatch, BODY + blob), "t.docx", "fix", [], "tester", user="u", review=False, agent=FakeAgent())
    job._run()
    s = job.state
    assert s["status"] == "waiting" and s["stage"] == "extract" and s["ask"]["reason"] == "blob"
    assert pipeline.summary(s)["ask"] is True
    try:
        job.resume()
        assert False, "review resume must be refused while the block question is open"
    except ValueError:
        pass
    job.set_block(1, [2], s["ask"]["candidates"][0]["text"].split("\n"))
    for _ in range(200):
        if job.state["status"] in ("done", "failed"):
            break
        job.wait(job.version, timeout=0.1)
    assert s["status"] == "done", s["error"]
    assert [it["number"] for it in s["items"]] == [1, 2] and s["ask"] is None
    texts = [para_text(p) for p in _paras(pipeline.Jobs().output(job.id, "u"))]
    # body cites [2] first -> swapped; the blob paragraph holds [1], the second entry is a new paragraph after it
    assert texts[0] == "See [1] and [2]." and texts[2].startswith("[1]B. Two") and texts[3].startswith("[2]A. One")


def test_append_writes_a_new_references_section_or_finishes_with_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB", tmp_path / "t.db")
    monkeypatch.setattr(pipeline, "lookup", _fake_lookup)
    body = '<w:p><w:r><w:t>Body cites [+1] only.</w:t></w:r></w:p>'
    job = pipeline.Job(_docx(monkeypatch, body), "t.docx", "smart", ["Attention is all you need"], "tester", user="u", review=False, agent=FakeAgent())
    job._run()
    assert job.state["status"] == "waiting" and job.state["ask"]["reason"] == "no_heading"
    job.set_block(None, [], None, append=True)
    for _ in range(200):
        if job.state["status"] in ("done", "failed"):
            break
        job.wait(job.version, timeout=0.1)
    assert job.state["status"] == "done", job.state["error"]
    texts = [para_text(p) for p in _paras(pipeline.Jobs().output(job.id, "u"))]
    assert texts[0] == "Body cites [1] only." and texts[1] == "References" and texts[2].startswith("[1]Attention is all you need")
    # no titles and no list: the job ends at once
    job2 = pipeline.Job(_docx(monkeypatch, body), "t.docx", "smart", [], "tester", user="u", review=False, agent=FakeAgent())
    job2._run()
    job2.set_block(None, [], None, append=True)
    for _ in range(100):
        if job2.state["status"] in ("done", "failed"):
            break
        job2.wait(job2.version, timeout=0.1)
    assert job2.state["status"] == "done" and job2.state["items"] == [] and job2.state["percent"] == 100
