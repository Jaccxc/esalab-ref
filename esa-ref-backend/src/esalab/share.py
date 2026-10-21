"""Share a finished job: a public read-only copy of its page, a 1200x630 card for link previews and a 1080x1080 one to post."""
from __future__ import annotations

import difflib
import html
import io
import os
import re
import secrets
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from esalab import db
from esalab.docx_track import norm_marks

INK, WHITE, SIGNAL, GRAY = "#0B0B0D", "#FFFFFF", "#2F4BF0", "#8A8A93"
_FD = Path(__file__).resolve().parents[2] / "fonts"  # the Docker image downloads these; a Windows dev box falls back to its own
FONTS = {"sans": [_FD / "InterTight.ttf", Path("C:/Windows/Fonts/arialbd.ttf")], "mono": [_FD / "JetBrainsMono.ttf", Path("C:/Windows/Fonts/consola.ttf")],
         "tc": [_FD / "NotoSansCJKtc-Bold.otf", Path("C:/Windows/Fonts/msjhbd.ttc")], "tcr": [_FD / "NotoSansCJKtc-Regular.otf", Path("C:/Windows/Fonts/msjh.ttc")]}
HIT_TEXT = {"copy": "複製連結", "image": "下載圖片", "native": "系統分享", "x": "X", "facebook": "Facebook", "threads": "Threads", "line": "LINE"}


def public_base(h) -> str:
    """Where this site is reached from outside: PUBLIC_URL when set (a real domain behind a proxy), else what the request says."""
    return os.environ.get("PUBLIC_URL", "").rstrip("/") or f"{h.get('x-forwarded-proto', 'http')}://{h.get('x-forwarded-host') or h.get('host', 'localhost')}"


def create(job_id: str, user: str) -> str:
    """The job's share token; one per job, made on first request."""
    with db.connect() as con:
        row = con.execute("SELECT token FROM shares WHERE job=?", (job_id,)).fetchone()
        if row:
            return row[0]
        token = secrets.token_urlsafe(9)
        con.execute("INSERT INTO shares (token, job, user, created) VALUES (?,?,?,?)", (token, job_id, user, time.time()))
    return token


def load(token: str) -> dict | None:
    """Everything the share page shows; the state comes from the job row, so it outlives the 30-day docx purge."""
    import json
    with db.connect() as con:
        row = con.execute("SELECT j.state, s.user, s.created FROM shares s JOIN jobs j ON j.id=s.job WHERE s.token=? AND j.deleted IS NULL", (token,)).fetchone()
    if not row:
        return None
    s = json.loads(row[0])
    return {"token": token, "user": row[1], "created": row[2], "job": s, "facts": facts(s)}


def facts(s: dict) -> dict:
    items = s.get("items", [])
    meta = [i.get("meta") or {} for i in items]
    checked = [i["check"] for i in items if i.get("check")]
    o = s.get("order") or {}
    return {"entries": sum(1 for i in items if i["kind"] == "fix"), "adds": sum(1 for i in items if i["kind"] == "add"),
            "changed": s.get("changed") or 0, "dup": sum(1 for i in items if i.get("status") == "duplicate"),
            "skipped": sum(1 for i in items if i.get("skip")), "kept": sum(1 for m in meta if m.get("kept")),
            "unsure": sum(1 for m in meta if m.get("match") in ("fuzzy", "none")),
            "passed": sum(1 for c in checked if c["ok"]), "checked": len(checked),
            "renumbered": len(o.get("renumber") or {}), "uncited": len(o.get("uncited") or []), "unknown": len(o.get("unknown") or []),
            "order_ok": o.get("ok"), "seconds": round(s.get("elapsed") or 0)}


def _font(fam: str, size: float, weight: int = 400):
    """One face per family at a weight; a missing family falls back to the next so the card always renders."""
    return _font_cached(fam, round(size), weight)


@lru_cache(maxsize=None)
def _font_cached(fam, size, weight):
    for fam in (fam, "tc", "tcr", "sans", "mono"):  # the design's own family first, then anything with glyphs
        for p in FONTS[fam]:
            if p.exists():
                f = ImageFont.truetype(str(p), size)
                try:  # the Google-fonts files are variable: pick the weight; a static face just ignores this
                    f.set_variation_by_axes([weight])
                except Exception:
                    pass
                return f
    return ImageFont.load_default(size)  # a box without any font: boxes for glyphs, still a PNG


_CJK_ONE = re.compile(r"[⺀-鿿豈-﫿＀-￯　-〿]")
_CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]+|[^\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]+")


def _runs(text: str, size: float, weight: int) -> list[tuple[str, ImageFont.FreeTypeFont]]:
    """Latin runs in Inter Tight, CJK runs in Noto (Pillow has no font fallback), as the browser does for the design."""
    return [(t, _font(("tc" if weight >= 600 else "tcr") if _CJK_ONE.match(t) else "sans", size, weight)) for t in _CJK.findall(text)]


def _mixed_width(d, runs) -> float:
    return sum(d.textlength(t, font=f) for t, f in runs)


def _draw_runs(d, x: float, base: float, runs, fill: str):
    for t, f in runs:
        d.text((x, base), t, font=f, fill=fill, anchor="ls")
        x += d.textlength(t, font=f)


def _wrap_runs(d, text: str, size: float, weight: int, width: float, lines: int) -> list[list]:
    """CSS -webkit-line-clamp: break after a CJK character or a separator when there is one, else anywhere; the last line gets an ellipsis."""
    out, cur = [], ""
    for ch in text:
        if _mixed_width(d, _runs(cur + ch, size, weight)) > width and cur:
            at = max((i + 1 for i, c in enumerate(cur[:-1]) if _CJK_ONE.match(c) or c in " _-."), default=0)
            out.append(cur[:at] or cur)
            cur = (cur[at:] if at else "") + ch
        else:
            cur += ch
    out.append(cur)
    if len(out) > lines:
        out, last = out[:lines], out[lines - 1]
        while last and _mixed_width(d, _runs(last + "…", size, weight)) > width:
            last = last[:-1]
        out[-1] = last + "…"
    return [_runs(line, size, weight) for line in out]


def _base(f, top: float, lh: float) -> float:
    """Where CSS puts the baseline of a line box of height lh: the glyph box (ascent+descent) centred in it."""
    asc, desc = f.getmetrics()
    return top + (lh - asc - desc) / 2 + asc


_TOK = re.compile(r"\*[^*]+\*|[^\s*]+|\*|\s+")


def bars(items: list[dict]) -> list[int]:
    """Per fix entry, how much the text moved: deleted + inserted non-space tokens (the web page's word diff)."""
    out = []
    for it in items:
        if it.get("kind") != "fix":
            continue
        a, b = it.get("original") or "", it.get("final") or ""
        if not b or a == b:
            out.append(0)
            continue
        A, B = (_TOK.findall(norm_marks(unicodedata.normalize("NFC", t))) for t in (a, b))
        n = 0
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, A, B, autojunk=False).get_opcodes():
            if op != "equal":
                n += sum(1 for t in A[i1:i2] + B[j1:j2] if not t.isspace())
        out.append(n)
    return out


def _bucket(vals: list[int], m: int) -> list[int]:
    """At most m bars: adjacent entries are summed into one bar once a paper has more references than bars fit."""
    if len(vals) <= m:
        return vals
    return [sum(vals[len(vals) * i // m:len(vals) * (i + 1) // m]) for i in range(m)]


def card(share: dict, square: bool = False) -> bytes:
    """The share image, drawn from the Claude Design artboards: 600x315 at 2x (og:image) or 360x360 at 3x.
    All numbers below are the design's CSS px; K scales them (drawn at 2x that and downsampled so edges are smooth)."""
    f, s = share["facts"], share["job"]
    k = 3 if square else 2
    K = k * 2
    W, H, PX, PT, PB = (360, 360, 24, 24, 24) if square else (600, 315, 30, 26, 24)
    im = Image.new("RGB", (W * K, H * K), INK)
    d = ImageDraw.Draw(im)
    X = lambda v: v * K  # noqa: E731
    cw = W - 2 * PX

    # header: mark (viewBox 0 -5.5 328.6 107.3 at 32.9px wide = 0.1 px per unit), name, report label
    u, hy = 0.1 * K, X(PT + 7.5)
    lx, ly = X(PX), hy - 53.65 * u
    d.rectangle([lx, ly + 5.5 * u, lx + 100 * u, ly + 105.5 * u], fill=WHITE)
    d.ellipse([lx + 123 * u, ly + 10.7 * u, lx + 212.6 * u, ly + 100.3 * u], outline=WHITE, width=round(14 * u))
    d.polygon([(lx + 272.2 * u, ly), (lx + 328.6 * u, ly + 105.5 * u), (lx + 215.8 * u, ly + 105.5 * u)], fill=SIGNAL)
    fn = _font("sans", X(12), 600)
    d.text((X(PX + 32.9 + 8), _base(fn, hy - X(7.5), X(15))), "ESA Lab", font=fn, fill=WHITE, anchor="ls")
    fr = _font("tcr", X(11), 400)
    d.text((X(W - PX), _base(fr, hy - X(7.5), X(15))), "參考文獻修訂報告", font=fr, fill="#8A8A93", anchor="rs")

    # bars: one per reference, bucketed and thinned so they fit their box
    vals = bars(s.get("items", []))
    if square:
        vals = _bucket(vals, 63)  # (312 - 3*(n-1)) / n >= 2px
        n = len(vals)
        bw, bg = ((cw - 3 * (n - 1)) / n if n else 0), 3
        bars_w = cw
    else:
        bw, bg = (4, 3) if len(vals) <= 43 else (3, 2) if len(vals) <= 60 else (2, 1)
        vals = _bucket(vals, 100)
        n = len(vals)
        bars_w = n * bw + (n - 1) * bg if n else 0
    caption = "每柱一條參考文獻" if n == f["entries"] else f"{f['entries']} 條參考文獻 · {n} 柱"
    mx = max(vals) if vals else 0
    lo, span = (10, 48) if square else (8, 48)
    heights = [(lo + span * v / mx) if v else 3 for v in vals]

    # title block: 2-line clamped file name, mode chip, date
    tsize, tlh = (26, 26 * 1.2) if square else (28, 28 * 1.2)
    top = PT + 15 + 26
    twidth = cw if square else cw - 28 - bars_w
    lines = _wrap_runs(d, s.get("filename") or "", X(tsize), 700, X(twidth), 2)
    # wide: the row is align-items flex-end, so a one-line title block drops to the bars column's bottom (56 + 6 + 12)
    y = top if square else top + max(0, 74 - (len(lines) * tlh + 10 + 17))
    for runs in lines:
        _draw_runs(d, X(PX), _base(runs[0][1] if runs else fn, X(y), X(tlh)), runs, WHITE)
        y += tlh
    y += 10
    chip = {"smart": "智慧模式", "fix": "修正模式", "add": "新增模式"}.get(s.get("mode") or "", s.get("mode") or "")
    fc = _font("tcr", X(11), 400)
    cwid = d.textlength(chip, font=fc) + X(12)
    d.rectangle([X(PX), X(y), X(PX) + cwid, X(y + 17)], outline="#3F3F46", width=round(K))
    d.text((X(PX + 6), _base(fc, X(y + 1), X(15))), chip, font=fc, fill=WHITE, anchor="ls")
    fm = _font("mono", X(11), 400)
    d.text((X(PX + 8) + cwid, _base(fm, X(y + 1), X(15))), time.strftime("%Y.%m.%d", time.localtime(s.get("started") or time.time())), font=fm, fill="#A1A1AA", anchor="ls")
    text_bottom = y + 17

    # stats + footer sit at the bottom (margin-top: auto)
    nsize, lsize, gap, pad = (34, 10, 10, 8) if square else (44, 11, 16, 10)
    foot_lh, foot_gap = 15, (14 if square else 16)
    cell_h = 1 + pad + nsize * 0.85 + 6 + lsize * 1.4
    foot_top = H - PB - foot_lh
    stats_top = foot_top - foot_gap - cell_h
    colw = (cw - 3 * gap) / 4
    cols = [(f["entries"], "條參考文獻"), (f["changed"], "處修訂"), (f["renumbered"], "處順序重編"), (f["adds"], "筆新增書目")]
    flab = _font("tcr", X(lsize), 500)
    while True:  # a four-digit count must stay inside its column: shrink the number face until it does
        fnum = _font("sans", X(nsize), 600)
        if nsize <= 20 or max(d.textlength(str(v), font=fnum) for v, _ in cols) <= X(colw):
            break
        nsize -= 2
    for i, (v, label) in enumerate(cols):
        cx = PX + i * (colw + gap)
        d.rectangle([X(cx), X(stats_top), X(cx + colw), X(stats_top) + K], fill="#3F3F46" if v else "#27272A")
        ny = stats_top + 1 + pad
        d.text((X(cx), _base(fnum, X(ny), X(nsize * 0.85))), str(v), font=fnum, fill=WHITE if v else "#3F3F46", anchor="ls")
        d.text((X(cx), _base(flab, X(ny + nsize * 0.85 + 6), X(lsize * 1.4))), label, font=flab, fill="#A1A1AA" if v else "#52525B", anchor="ls")
    if f["checked"]:
        t1, f1 = "審查一次通過 ", _font("tcr", X(11), 400)
        d.text((X(PX), _base(f1, X(foot_top), X(foot_lh))), t1, font=f1, fill="#A1A1AA", anchor="ls")
        f2 = _font("sans", X(11), 600)
        d.text((X(PX) + d.textlength(t1, font=f1), _base(f2, X(foot_top), X(foot_lh))), f"{round(f['passed'] / f['checked'] * 100)}%", font=f2, fill=WHITE, anchor="ls")
    f3 = _font("mono", X(10), 400)
    d.text((X(W - PX), _base(f3, X(foot_top), X(foot_lh))), "esalab", font=f3, fill="#6B6B73", anchor="rs")

    # bars block: wide = right of the title, bottoms aligned; square = full width above the stats
    fcap = _font("tcr", X(10), 400)
    if square:
        cap_top = stats_top - 18 - 12
        bars_bottom = cap_top - 6
        bars_top = max(bars_bottom - 60, text_bottom + 6)
        bx = PX
        d.text((X(PX), _base(fcap, X(cap_top), X(12))), caption, font=fcap, fill="#6B6B73", anchor="ls")
    else:
        bars_bottom = max(text_bottom, top + 74) - 12 - 6
        bars_top = bars_bottom - 56
        bx = W - PX - bars_w
        d.text((X(W - PX), _base(fcap, X(bars_bottom + 6), X(12))), caption, font=fcap, fill="#6B6B73", anchor="rs")
    avail = bars_bottom - bars_top
    for i, (v, h) in enumerate(zip(vals, heights)):
        h = min(h, avail)
        x0 = bx + i * (bw + bg)
        d.rectangle([X(x0), X(bars_bottom - h), X(x0 + bw), X(bars_bottom)], fill=SIGNAL if v else "#3F3F46")

    im = im.resize((W * k, H * k), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def png(token: str, square: bool = False) -> bytes | None:
    """Cached card; the purge drops it after 30 days and the next request draws it again."""
    col = "png_sq" if square else "png"
    with db.connect() as con:
        row = con.execute(f"SELECT {col} FROM shares WHERE token=?", (token,)).fetchone()
    if row and row[0]:
        return row[0]
    share = load(token)
    if not share:
        return None
    data = card(share, square)
    with db.connect() as con:
        con.execute(f"UPDATE shares SET {col}=?, png_at=? WHERE token=?", (data, time.time(), token))
    return data


def page(share: dict, base: str) -> str:
    """What a crawler sees: Open Graph tags; a browser is sent on to the SPA route."""
    t = html.escape(f"{share['job'].get('filename', '')} · 參考文獻修訂報告")
    f = share["facts"]  # same text as the frontend's blurbOf
    parts = [f"{f['entries']} 條 reference"] + [f"{f[k]} {label}" for k, label in (("changed", "筆修訂"), ("adds", "筆新增書目"), ("renumbered", "處順序重編")) if f[k]]
    desc = html.escape(f"{share['job'].get('filename', '')} 的參考文獻修訂報告：{'，'.join(parts)}")
    tok = html.escape(share["token"])
    return (f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{t}</title>'
            f'<meta property="og:title" content="{t}"><meta property="og:description" content="{desc}">'
            f'<meta property="og:image" content="{html.escape(base)}/api/share/{tok}/card.png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
            f'<meta name="twitter:card" content="summary_large_image"><meta http-equiv="refresh" content="0;url=/#/s/{tok}"></head>'
            f'<body><a href="/#/s/{tok}">{t}</a></body></html>')
