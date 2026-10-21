"""Share a finished job: a public read-only copy of its page, a 1200x630 card for link previews."""
from __future__ import annotations

import html
import io
import os
import secrets
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from esalab import db

INK, WHITE, SIGNAL, GRAY = "#0B0B0D", "#FFFFFF", "#2F4BF0", "#8A8A93"
# One bold CJK face is enough for the card: the Docker image downloads Noto; a Windows dev box has JhengHei.
FONTS = [Path(__file__).resolve().parents[2] / "fonts/NotoSansCJKtc-Bold.otf", Path("C:/Windows/Fonts/msjhbd.ttc")]
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


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in FONTS:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)  # tests on a box without a CJK font: boxes instead of glyphs, still a PNG


def _fit(d: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    while d.textlength(text, font=font) > width and len(text) > 1:
        text = text[:-2] + "…"
    return text


def card(share: dict) -> bytes:
    """The 1200x630 og:image. Left: file name, four numbers, footer. Right: the brand mark blown up into a column
    (square, ring, blue triangle) so the card reads as ESA Lab's at a glance. Text sits on baselines so gaps are real gaps."""
    f, s = share["facts"], share["job"]
    im = Image.new("RGB", (1200, 630), INK)
    d = ImageDraw.Draw(im)
    x, w = 968, 168  # the mark column: three 168px shapes, 20px apart, from top margin to bottom margin
    d.rectangle([x, 43, x + w, 43 + w], fill=WHITE)
    d.ellipse([x, 231, x + w, 231 + w], outline=WHITE, width=22)
    d.polygon([(x + w / 2, 419), (x + w, 419 + w), (x, 419 + w)], fill=SIGNAL)
    d.text((64, 74), "ESA Lab", font=_font(30), fill=WHITE, anchor="lm")
    d.text((196, 75), "參考文獻修訂報告", font=_font(22), fill=GRAY, anchor="lm")
    d.text((64, 232), _fit(d, s.get("filename") or "", _font(54), 840), font=_font(54), fill=WHITE, anchor="ls")
    small = _font(22)
    cols = [(f["entries"], "條 reference"), (f["changed"], "筆修訂"), (f["adds"], "筆新增書目"), (f["renumbered"], "處順序重編")]
    size = 112  # columns are as wide as their widest text; big numbers shrink the row until it fits the 840px left area
    while True:
        big = _font(size)
        widths = [max(d.textlength(str(n), font=big) + 48, d.textlength(label, font=small) + 48, 218) for n, label in cols]
        if sum(widths) - 48 <= 840 or size <= 64:
            break
        size -= 8
    cx = 64
    for (n, label), w in zip(cols, widths):
        d.text((cx, 436), str(n), font=big, fill=WHITE, anchor="ls")
        d.text((cx + 4, 484), label, font=small, fill=GRAY, anchor="ls")
        cx += w
    d.line([64, 540, 904, 540], fill="#27272A", width=2)
    rate = f"審查一次通過 {round(f['passed'] / f['checked'] * 100)}%" if f["checked"] else ""
    d.text((64, 584), " · ".join(x for x in (rate, f"{s.get('mode', '')} 模式", "esalab 參考文獻修訂工具") if x), font=_font(20), fill=GRAY, anchor="lm")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def png(token: str) -> bytes | None:
    """Cached card; the purge drops it after 30 days and the next request draws it again."""
    with db.connect() as con:
        row = con.execute("SELECT png FROM shares WHERE token=?", (token,)).fetchone()
    if row and row[0]:
        return row[0]
    share = load(token)
    if not share:
        return None
    data = card(share)
    with db.connect() as con:
        con.execute("UPDATE shares SET png=?, png_at=? WHERE token=?", (data, time.time(), token))
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
