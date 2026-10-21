from esalab import lookup as lk

CR = [{"DOI": "10.1109/tencon.2017.8228098", "title": ["Sitting posture recognition for computer users"]},
      {"DOI": "10.1109/hnicem.2017.8269473", "title": ["Sitting posture assessment using computer vision"], "issued": {"date-parts": [[2017, 12]]}}]


def test_ieee_link_resolves_by_title_hint(monkeypatch):
    seen = {}
    monkeypatch.setattr(lk, "_crossref", lambda t, prefix=None, rows=5: seen.update(t=t, prefix=prefix) or CR)
    out = lk.lookup_live("https://ieeexplore.ieee.org/document/8269473", hint="Sitting posture assessment using computer vision")
    assert out["match"] == "exact" and out["doi"] == "10.1109/hnicem.2017.8269473" and out["year"] == 2017
    assert seen == {"t": "Sitting posture assessment using computer vision", "prefix": "10.1109"}
    out = lk.lookup_live("https://ieeexplore.ieee.org/abstract/document/999?x=1", hint="Sitting posture assessment using computer vision")
    assert out["match"] == "none" and "DOI" in out["error"]
    assert lk.lookup_live("https://ieeexplore.ieee.org/document/8269473")["match"] == "none"  # no hint: nothing to search with


def test_throttled_sources_are_reported(monkeypatch):
    class R:
        def __init__(self, code): self.status_code = code
        def json(self): return {"results": [], "message": {"items": []}}
    monkeypatch.setattr(lk.httpx, "get", lambda *a, **k: R(429))
    assert lk._openalex("x") == [] and lk._crossref("x") == []
    assert sorted(t["source"] for t in lk.throttled()) == ["crossref", "openalex"] and lk.throttled()[0]["status"] == 429
    monkeypatch.setattr(lk.httpx, "get", lambda *a, **k: R(200))
    lk._openalex("x")
    assert [t["source"] for t in lk.throttled()] == ["crossref"]
    lk.THROTTLED.clear()
