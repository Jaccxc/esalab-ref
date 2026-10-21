"""Trusted bibliographic metadata: DOI/arXiv direct, else Crossref exact title, OpenAlex, Semantic Scholar, then fuzzy."""
from __future__ import annotations

import html
import json
import re
import time

import os

import httpx

from esalab import db

CACHE_TTL = 30 * 24 * 3600  # bibliographic data is stable; re-search after a month

H = {"User-Agent": "esalab-refs/0.1 (mailto:esalab@example.com)"}
THROTTLED: dict[str, dict] = {}  # source -> {status, at} of its last refusal; cleared by the next good answer


def _ok(source: str, r: httpx.Response) -> bool:
    if r.status_code == 200:
        THROTTLED.pop(source, None)
        return True
    THROTTLED[source] = {"status": r.status_code, "at": time.time()}
    return False


def throttled() -> list[dict]:
    """Sources that refused us within the last hour (429 = free quota/rate limit); shown site-wide."""
    return [{"source": k} | v for k, v in THROTTLED.items() if time.time() - v["at"] < 3600]
MONTHS = [None, "Jan.", "Feb.", "Mar.", "Apr.", "May", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec."]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", html.unescape(s or "").lower()).strip()


def _crossref(title: str, prefix: str | None = None, rows: int = 5) -> list[dict]:
    r = httpx.get(
        "https://api.crossref.org/works",
        params={"query.bibliographic": title, "rows": rows,
                "select": "title,author,issued,container-title,short-container-title,volume,issue,page,DOI,type,event,article-number,publisher,publisher-location"}
        | ({"filter": f"prefix:{prefix}"} if prefix else {}),
        headers=H, timeout=30,
    )
    if not _ok("crossref", r):  # outage or throttling: no answer rather than a failed lookup
        return []
    return r.json()["message"]["items"]


def _from_crossref(h: dict) -> dict:
    dp = (h.get("issued") or {}).get("date-parts") or [[None]]
    ev = h.get("event") or {}
    start = ((ev.get("start") or {}).get("date-parts") or [[None]])[0]
    end = ((ev.get("end") or {}).get("date-parts") or [[None]])[0]
    return {
        "source": "crossref",
        "type": h.get("type"),
        "title": html.unescape((h.get("title") or [""])[0]),
        "authors": [{"given": a.get("given"), "family": a.get("family"), "name": a.get("name")} for a in h.get("author", [])],
        "year": dp[0][0] if dp and dp[0] else None,
        "month": MONTHS[dp[0][1]] if dp and len(dp[0]) > 1 and dp[0][1] else None,
        "venue": html.unescape((h.get("container-title") or [None])[0] or "") or None,
        "venue_short": html.unescape((h.get("short-container-title") or [None])[0] or "") or None,
        "volume": h.get("volume"),
        "issue": h.get("issue"),
        "pages": h.get("page"),
        "article_number": h.get("article-number"),
        "doi": h.get("DOI"),
        "publisher": h.get("publisher"),
        "publisher_location": h.get("publisher-location"),
        "event": {"name": ev.get("name"), "location": ev.get("location"), "start": start, "end": end} if ev else None,
    }


def _openalex(title: str) -> list[dict]:
    key = os.environ.get("OPENALEX_API_KEY")
    r = httpx.get(
        "https://api.openalex.org/works",
        params={"search": title, "per-page": 5, "sort": "cited_by_count:desc",
                "select": "title,authorships,publication_year,publication_date,primary_location,biblio,doi,type"} | ({"api_key": key} if key else {}),
        headers=H, timeout=30,
    )
    if not _ok("openalex", r):  # anonymous daily budget exhausted or throttled: no answer rather than a failed lookup
        return []
    return r.json()["results"]


def _from_openalex(h: dict) -> dict:
    b = h.get("biblio") or {}
    src = ((h.get("primary_location") or {}).get("source") or {})
    date = h.get("publication_date") or ""
    m = int(date[5:7]) if len(date) >= 7 else 0
    return {
        "source": "openalex",
        "type": h.get("type"),
        "title": h.get("title"),
        "authors": [{"name": a["author"]["display_name"]} for a in h.get("authorships", []) if a.get("author")],
        "year": h.get("publication_year"),
        "month": MONTHS[m] if m else None,
        "venue": src.get("display_name"),
        "venue_short": None,
        "volume": b.get("volume"),
        "issue": b.get("issue"),
        "pages": "-".join(p for p in (b.get("first_page"), b.get("last_page")) if p) or None,
        "article_number": None,
        "doi": (h.get("doi") or "").removeprefix("https://doi.org/") or None,
        "publisher": None,
        "publisher_location": None,
        "event": None,
    }


DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
# IEEE Xplore links carry only the article number (= the DOI suffix); the site blocks server-side reads, so the title must find it
IEEE_RE = re.compile(r"ieeexplore\.ieee\.org/(?:abstract/)?document/(\d+)|[?&]arnumber=(\d+)", re.I)
ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)|^(?:arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)$", re.I)


def _doi(doi: str) -> dict | None:
    r = httpx.get(f"https://api.crossref.org/works/{doi}", headers=H, timeout=30)
    if r.status_code == 200:
        return _from_crossref(r.json()["message"])
    # not a Crossref DOI (arXiv and other DataCite DOIs): doi.org content negotiation gives CSL JSON
    r = httpx.get(f"https://doi.org/{doi}", headers=H | {"Accept": "application/vnd.citationstyles.csl+json"}, follow_redirects=True, timeout=30)
    if r.status_code != 200:
        return None
    h = r.json()
    for k in ("title", "container-title", "short-container-title"):  # CSL uses strings where Crossref uses lists
        if isinstance(h.get(k), str):
            h[k] = [h[k]]
    return _from_crossref(h) | {"source": "datacite"}


def _semanticscholar(title: str) -> list[dict]:
    r = httpx.get("https://api.semanticscholar.org/graph/v1/paper/search",
                  params={"query": title, "limit": 5, "fields": "title,authors,year,venue,externalIds"},
                  headers=H | ({"x-api-key": key} if (key := os.environ.get("S2_API_KEY")) else {}), timeout=30)
    if not _ok("semanticscholar", r):  # shared anonymous rate limit: treat as "no answer"
        return []
    return r.json().get("data") or []


def _from_s2(h: dict) -> dict:
    return {"source": "semanticscholar", "type": None, "title": h.get("title"),
            "authors": [{"name": a.get("name")} for a in h.get("authors", [])], "year": h.get("year"), "month": None,
            "venue": h.get("venue") or None, "venue_short": None, "volume": None, "issue": None, "pages": None,
            "article_number": None, "doi": (h.get("externalIds") or {}).get("DOI"), "publisher": None,
            "publisher_location": None, "event": None}


def lookup(query: str, hint: str | None = None) -> dict:
    """Cached in SQLite (table lookups) so the same title/DOI is never fetched twice; `none` results are not
    cached, so a retry after a typo fix or a newly indexed paper gets a fresh search. hint = the entry's own title."""
    key = (norm(query) or query.strip()) + (f"|{norm(hint)}" if hint and IEEE_RE.search(query) else "")
    with db.connect() as con:
        row = con.execute("SELECT result FROM lookups WHERE query=? AND created>?", (key, time.time() - CACHE_TTL)).fetchone()
    if row:
        return json.loads(row[0]) | {"cached": True}
    out = lookup_live(query, hint)
    if out["match"] != "none":
        with db.connect() as con:
            con.execute("INSERT OR REPLACE INTO lookups VALUES (?,?,?)", (key, time.time(), json.dumps(out, ensure_ascii=False)))
    return out


def lookup_live(query: str, hint: str | None = None) -> dict:
    """Metadata dict with `match` in {exact, fuzzy, none} and `candidates` (other plausible works) for review.
    query may be a title, a DOI, a doi.org/arXiv URL, an arXiv id or an IEEE Xplore link (needs hint = the entry's title).
    exact results are trustworthy."""
    query = query.strip()
    ieee = IEEE_RE.search(query)
    if ieee:
        n = ieee.group(1) or ieee.group(2)
        for c in (_from_crossref(h) for h in (_crossref(hint, prefix="10.1109", rows=20) if hint else [])):
            if (c.get("doi") or "").lower().endswith(f".{n}"):
                return c | {"match": "exact", "candidates": []}
        return {"title": hint or query, "match": "none", "source": None, "candidates": [],
                "error": "IEEE Xplore 連結沒有 DOI，網站也擋住伺服器讀取；請改貼該頁顯示的 DOI（10.1109/…）"}
    m = ARXIV_RE.search(query)
    doi = DOI_RE.search(query).group().rstrip(".,;)") if DOI_RE.search(query) else (f"10.48550/arXiv.{(m.group(1) or m.group(2)).split('v')[0]}" if m else None)
    if doi:
        hit = _doi(doi)
        return hit | {"match": "exact", "candidates": []} if hit else {"title": query, "match": "none", "source": None, "candidates": []}
    want = norm(query)
    cr = [_from_crossref(h) for h in _crossref(query)]
    oa = [_from_openalex(h) for h in _openalex(query)]
    cands = cr[:3] + oa[:2]
    for c in cr + oa:
        if norm(c["title"]) == want:
            return c | {"match": "exact", "candidates": [x for x in cands if x is not c][:3]}
    for h in _semanticscholar(query):
        if norm(h.get("title")) == want:
            c = (_doi((h.get("externalIds") or {}).get("DOI")) if (h.get("externalIds") or {}).get("DOI") else None) or _from_s2(h)
            return c | {"match": "exact", "candidates": cands[:3]}
    if cands:
        return cands[0] | {"match": "fuzzy", "candidates": cands[1:4]}
    return {"title": query, "match": "none", "source": None, "candidates": []}
