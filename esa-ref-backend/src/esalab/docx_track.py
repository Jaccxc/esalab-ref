"""Read reference entries from a .docx and write changes back as Word tracked changes (修訂模式).

A .docx is a zip; tracked changes are <w:ins>/<w:del> wrappers in word/document.xml.
No Word installation needed.
"""
from __future__ import annotations

import copy
import difflib
import unicodedata
import io
import re
import zipfile
from datetime import datetime, timezone

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
HEADING_RE = re.compile(r"^\s*(references?|bibliography|參考文獻|參考資料|引用文獻)\s*$", re.I)
LABEL_RE = re.compile(r"^\s*(\[\d+\])[\s　]*")
NUM_RE = re.compile(r"^\s*(\[\d+\]|\d+[.)])[\s　]*")  # any hand-typed number a user-confirmed entry may start with
REF_HINT_RE = re.compile(r"(19|20)\d\d|vol\.|pp\.|doi|https?://|[“\"]")  # looks like a reference entry
_MARK_RE = re.compile(r"(\*\*.+?\*\*|\*.+?\*)")


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


def para_text(p) -> str:
    return "".join(p.xpath(".//w:t/text()", namespaces=NS))


def para_lines(p) -> str:
    """Like para_text, but manual line breaks (<w:br/>) become newlines: a list pasted into one paragraph."""
    return "".join("\n" if x.tag == w("br") else (x.text or "") for x in p.xpath(".//w:t | .//w:br", namespaces=NS))


def para_marked_text(p) -> str:
    """Paragraph text with italic runs wrapped in *...* (adjacent italic runs merged)."""
    s = ""
    for r in p.xpath("./w:r | ./w:hyperlink/w:r | ./w:ins/w:r", namespaces=NS):
        t = "".join(r.xpath("./w:t/text()", namespaces=NS))
        if t:
            s += f"*{t}*" if r.find("w:rPr/w:i", NS) is not None else t
    return norm_marks(s.replace("**", ""))


def norm_marks(s: str) -> str:
    """Canonical '*italic*' markup: split runs merged (*IEEE* *Trans.* -> *IEEE Trans.*), spaces and trailing
    comma outside the span (*Health, * -> *Health*, ; a dot stays: *Eng.*), so the same-looking text compares equal."""
    s = re.sub(r"\*(\s+)\*", r"\1", s)
    return re.sub(r"\*(\s*)([^*]*?)([\s,;:]*)\*", r"\1*\2*\3", s)


def _is_heading(p) -> bool:
    style = p.find("w:pPr/w:pStyle", NS)
    return style is not None and style.get(w("val"), "").lower().startswith(("heading", "title", "標題"))


def _runs(text: str, base_rpr) -> list:
    """Split '*italic*' / '**bold**' markup into <w:r> elements, copying base run props."""
    runs = []
    for tok in _MARK_RE.split(text):
        if not tok:
            continue
        bold = tok.startswith("**")
        italic = not bold and tok.startswith("*")
        tok = tok.strip("*") if (bold or italic) else tok
        r = etree.Element(w("r"))
        rpr = copy.deepcopy(base_rpr) if base_rpr is not None else etree.Element(w("rPr"))
        for name, on in (("b", bold), ("i", italic)):
            for old in rpr.findall(f"w:{name}", NS):
                rpr.remove(old)
            if on:
                rpr.append(etree.Element(w(name)))
        if len(rpr):
            r.append(rpr)
        for k, piece in enumerate(tok.split("	")):  # '	' -> <w:tab/>: entries are "[n]<tab>text" with a hanging indent
            if k:
                etree.SubElement(r, w("tab"))
            if piece:
                t = etree.SubElement(r, w("t"))
                t.text = piece
                t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        runs.append(r)
    return runs


class Tracker:
    def __init__(self, author: str, start_id: int):
        self.author, self.next_id = author, start_id
        self.date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def mark(self, tag: str):
        el = etree.Element(w(tag))
        el.set(w("id"), str(self.next_id))
        el.set(w("author"), self.author)
        el.set(w("date"), self.date)
        self.next_id += 1
        return el

    def new_paragraph(self, text: str, template_p):
        """A paragraph whose runs and paragraph mark are all tracked insertions."""
        p = etree.Element(w("p"))
        ppr = template_p.find("w:pPr", NS) if template_p is not None else None
        ppr = copy.deepcopy(ppr) if ppr is not None else etree.Element(w("pPr"))
        for old in ppr.findall("w:rPr", NS) + ppr.findall("w:numPr", NS):
            ppr.remove(old)
        mark_rpr = etree.SubElement(ppr, w("rPr"))
        mark_rpr.append(self.mark("ins"))
        p.append(ppr)
        base_rpr = template_p.find("w:r/w:rPr", NS) if template_p is not None else None
        ins = self.mark("ins")
        for r in _runs(text, base_rpr):
            ins.append(r)
        p.append(ins)
        return p

    def replace_paragraph_text(self, p, text: str):
        """Tracked word-level diff of the paragraph against text, so a fixed entry shows only what changed.
        Whole delete + insert when the runs hold more than text (fields, breaks, links) or little is shared."""
        base_rpr = p.find(".//w:r/w:rPr", NS)
        base_rpr = copy.deepcopy(base_rpr) if base_rpr is not None else None
        if base_rpr is not None:
            for name in ("i", "b"):
                for old in base_rpr.findall(f"w:{name}", NS):
                    base_rpr.remove(old)
        _merge_runs(p)
        runs = p.xpath("./w:r", namespaces=NS)
        texts = [_run_text(r) for r in runs]
        old = []  # (token, (italic, bold), run index)
        if runs and None not in texts and not p.xpath("./w:hyperlink", namespaces=NS):
            for i, (r, t) in enumerate(zip(runs, texts)):
                st = _style(r.find("w:rPr", NS))
                old += [(tok, st, i) for tok in _TOK_RE.findall(t)]
        new = _styled_tokens(text)
        nfc = unicodedata.normalize  # composed vs decomposed accents are the same word; the untouched text keeps its own form
        key = lambda tok, st: (nfc("NFC", tok), None if tok.isspace() else st)  # a space is the same space whatever its style
        sm = difflib.SequenceMatcher(None, [key(o[0], o[1]) for o in old], [key(t, st) for t, st in new], autojunk=False)
        if not old or sm.ratio() < 0.5:
            for r in p.xpath("./w:r | ./w:hyperlink/w:r", namespaces=NS):
                for t in r.findall("w:t", NS):
                    t.tag = w("delText")
                d = self.mark("del")
                r.addprevious(d)
                d.append(r)
            ins = self.mark("ins")
            for r in _runs(text, base_rpr):
                ins.append(r)
            p.append(ins)
            return
        anchor = runs[0].getprevious()
        for r in runs:
            p.remove(r)
        out = []

        def old_runs(toks, tag):  # consecutive old tokens, one run per original run (its rPr kept)
            for i in sorted({t[2] for t in toks}):
                out_r = _r("".join(t[0] for t in toks if t[2] == i), runs[i].find("w:rPr", NS), tag)
                yield out_r

        for op, a, b, c, d in sm.get_opcodes():
            if op == "equal":
                out += list(old_runs(old[a:b], "t"))
            if op in ("replace", "delete"):
                dl = self.mark("del")
                dl.extend(old_runs(old[a:b], "delText"))
                out.append(dl)
            if op in ("replace", "insert"):
                ins = self.mark("ins")
                for st in dict.fromkeys(t[1] for t in new[c:d]):  # group by style, in order of first appearance
                    rpr = copy.deepcopy(base_rpr) if base_rpr is not None else etree.Element(w("rPr"))
                    for name, on in (("i", st[0]), ("b", st[1])):
                        if on:
                            rpr.append(etree.Element(w(name)))
                    ins.append(_r("".join(t[0] for t in new[c:d] if t[1] == st), rpr if len(rpr) else None, "t"))
                out.append(ins)
        for el in out:
            if anchor is None:
                p.insert(0, el)
            else:
                anchor.addnext(el)
            anchor = el

    def rewrite_runs(self, p, fn) -> bool:
        """Apply fn(text) -> text to the paragraph's plain text; every differing span becomes a tracked del/ins on
        the runs it covers, so a citation Word split over runs of different formatting ("[17]" "–[" "19]") is
        still seen whole. Returns True if anything changed."""
        _merge_runs(p)
        runs = [r for r in p.findall("w:r", NS) if _plain(r)]
        texts = [r.find("w:t", NS).text or "" for r in runs]
        old = "".join(texts)
        new = fn(old)
        if new == old or not runs:
            return False
        starts = [sum(len(t) for t in texts[:i]) for i in range(len(texts))]
        ops = [op for op in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes() if op[0] != "equal"]
        for _, a, b, c, d in reversed(ops):  # back to front, so the offsets of untouched earlier text stay valid
            idx = [i for i, t in enumerate(texts) if starts[i] < b and starts[i] + len(t) > a] \
                or [max(i for i in range(len(runs)) if starts[i] <= a)]  # pure insertion: the run that holds/ends at a
            for i in idx:
                r, t, lo, hi = runs[i], texts[i], max(a, starts[i]) - starts[i], min(b, starts[i] + len(texts[i])) - starts[i]
                after = []
                if hi > lo:
                    dl = self.mark("del")
                    dr = etree.SubElement(dl, w("r"))
                    if (rpr := r.find("w:rPr", NS)) is not None:
                        dr.append(copy.deepcopy(rpr))
                    dt = etree.SubElement(dr, w("delText"))
                    dt.text = t[lo:hi]
                    dt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    after.append(dl)
                if i == idx[-1]:
                    ins = self.mark("ins")
                    ins.extend(_runs(new[c:d], runs[idx[0]].find("w:rPr", NS)))
                    after.append(ins)
                if t[hi:]:
                    tail = copy.deepcopy(r)
                    tail.find("w:t", NS).text = t[hi:]
                    tail.find("w:t", NS).set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                    after.append(tail)
                anchor = r
                for el in after:
                    anchor.addnext(el)
                    anchor = el
                r.find("w:t", NS).text = texts[i] = t[:lo]
                r.find("w:t", NS).set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
                if not t[:lo]:
                    p.remove(r)
        return True


_TOK_RE = re.compile(r"\S+|\s+")


def _run_text(r) -> str | None:
    """Text of a run made of rPr / t / tab only (tab -> '\t'); None when it holds anything else (field, break, drawing)."""
    out = ""
    for c in r:
        if c.tag == w("t"):
            out += c.text or ""
        elif c.tag == w("tab"):
            out += "\t"
        elif c.tag != w("rPr"):
            return None
    return out


def _style(rpr) -> tuple[bool, bool]:
    return (rpr is not None and rpr.find("w:i", NS) is not None, rpr is not None and rpr.find("w:b", NS) is not None)


def _styled_tokens(text: str) -> list[tuple[str, tuple[bool, bool]]]:
    """Words and spaces of '*italic*' / '**bold**' markup text, each with its style."""
    out = []
    for seg in _MARK_RE.split(text):
        if not seg:
            continue
        bold = seg.startswith("**")
        italic = not bold and seg.startswith("*")
        out += [(tok, (italic, bold)) for tok in _TOK_RE.findall(seg.strip("*") if (bold or italic) else seg)]
    return out


def _r(text: str, rpr, tag: str):
    """One run of text with the given rPr (copied); '\t' -> <w:tab/>; tag is t or delText."""
    r = etree.Element(w("r"))
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    for k, piece in enumerate(text.split("\t")):
        if k:
            etree.SubElement(r, w("tab"))
        if piece:
            t = etree.SubElement(r, w(tag))
            t.text = piece
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return r


def _plain(r) -> bool:
    """A run holding exactly one text node (no tab, field, break...)."""
    return len(r.findall("w:t", NS)) == 1 and len(r) - (r.find("w:rPr", NS) is not None) == 1


def _merge_runs(p):
    """Join adjacent plain-text runs with identical rPr (Word splits text at every edit)."""
    def key(r):
        rpr = r.find("w:rPr", NS)
        return etree.tostring(rpr) if rpr is not None else b""
    prev = None
    for r in list(p.findall("w:r", NS)):
        plain = _plain(r)
        if prev is not None and plain and prev.getnext() is r and key(prev) == key(r):
            pt = prev.find("w:t", NS)
            pt.text = (pt.text or "") + (r.find("w:t", NS).text or "")
            pt.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            p.remove(r)
            continue
        prev = r if plain else None


class Doc:
    def __init__(self, docx_bytes: bytes, block: dict | None = None):
        """block: the user's answer when the list could not be read automatically:
        {"heading": idx|None, "paras": [idx...], "entries"?: [text...]}. With entries, entry k replaces paragraph
        paras[k] (or is appended when there are more entries than paragraphs); without, the paragraphs' own text is used."""
        self.zin = zipfile.ZipFile(io.BytesIO(docx_bytes))
        self.root = etree.fromstring(self.zin.read("word/document.xml"))
        self.body = self.root.find("w:body", NS)
        self.paras = self.body.findall("w:p", NS)
        self.block = block
        self.numfmt = self._num_formats()

    def _num_formats(self) -> dict[str, str]:
        """numId -> level-0 lvlText of Word's automatic numbering ("[%1]", "%1.", bullets...).
        shortcut: only level 0 and no lvlOverride, upgrade if a nested reference list ever shows up."""
        if "word/numbering.xml" not in self.zin.namelist():
            return {}
        root = etree.fromstring(self.zin.read("word/numbering.xml"))
        abstract = {a.get(w("abstractNumId")): a for a in root.findall("w:abstractNum", NS)}
        out = {}
        for n in root.findall("w:num", NS):
            a = abstract.get(n.find("w:abstractNumId", NS).get(w("val")))
            lvl = a.find("w:lvl[@w:ilvl='0']/w:lvlText", NS) if a is not None else None
            out[n.get(w("numId"))] = lvl.get(w("val"), "") if lvl is not None else ""
        return out

    def _auto_number(self, p) -> str | None:
        """The lvlText if the paragraph is numbered by Word itself (the number is not in its text)."""
        n = p.find("w:pPr/w:numPr/w:numId", NS)
        return self.numfmt.get(n.get(w("val")), "") if n is not None else None

    @property
    def relabel(self) -> bool:
        """True when the entries' [n] are not literal text (Word numbering or a user-confirmed block): every entry
        must then be rewritten so the label becomes hand-typed text."""
        return self.block is not None or any(self._auto_number(self.paras[j]) is not None for j in self.reference_block()[1])

    def _heading(self) -> int | None:
        for i, p in enumerate(self.paras):
            t = para_text(p)
            if HEADING_RE.match(t) and (_is_heading(p) or len(t) < 20):
                return i
        return None

    def suggest(self) -> dict:
        """What to ask the user when no entries were found: the paragraphs after the heading (or after the last
        heading of the document) as candidates. blob=True when the list seems pasted into one or two paragraphs."""
        heading = self._heading()
        if heading is None:
            hs = [i for i, p in enumerate(self.paras) if _is_heading(p)]
            start = hs[-1] + 1 if hs else max(0, len(self.paras) - 60)
        else:
            start = heading + 1
        cands = []
        for j in range(start, len(self.paras)):
            p = self.paras[j]
            t = para_lines(p).strip()
            if heading is not None and _is_heading(p):
                break
            if not t:
                continue
            m = NUM_RE.match(t)
            cands.append({"index": j, "text": t, "numbered": self._auto_number(p) or (m.group(1) if m else None),
                          "likely": bool(REF_HINT_RE.search(t))})
        blob = 0 < len(cands) <= 2 and any(("\n" in c["text"] or len(c["text"]) > 300) and c["likely"] for c in cands)  # a long unrelated paragraph is not a list
        reason = "no_heading" if heading is None else "empty" if not cands else "blob" if blob else "no_labels"
        return {"reason": reason, "heading": heading, "candidates": cands, "blob": blob}

    def reference_block(self) -> tuple[int | None, list[int]]:
        """(heading paragraph index, indexes of entry paragraphs after it: `[n]` typed in the text or `[n]` by Word numbering)."""
        if self.block is not None:
            return self.block.get("heading"), list(self.block.get("paras") or [])
        i = self._heading()
        if i is None:
            return None, []
        entries = []
        for j in range(i + 1, len(self.paras)):
            q = self.paras[j]
            tq = para_text(q).strip()
            if _is_heading(q):
                break
            if LABEL_RE.match(tq) or "[%" in (self._auto_number(q) or ""):
                entries.append(j)
            elif entries and tq:
                break  # first non-entry paragraph after the list ends the block
        return i, entries

    def entries(self) -> list[dict]:
        """[{index: paragraph index or None (a confirmed entry with no paragraph yet), label: "[n]", text}]."""
        _, idx = self.reference_block()
        if self.block is not None and "entries" in self.block:
            return [{"index": idx[k] if k < len(idx) else None, "label": f"[{k + 1}]", "text": NUM_RE.sub("", t, count=1).strip()}
                    for k, t in enumerate(self.block["entries"]) if t.strip()]
        out = []
        for k, j in enumerate(idx, 1):
            marked = para_marked_text(self.paras[j])
            m = LABEL_RE.match(para_text(self.paras[j]))
            label = m.group(1) if m and self.block is None else f"[{k}]"  # Word-numbered / confirmed: the label is the position
            out.append({"index": j, "label": label, "text": NUM_RE.sub("", marked, count=1).strip()})
        return out

    def _unlink_fields(self, idx: list[int]):
        """EndNote wraps the whole list in one `ADDIN EN.REFLIST` field (begin in [1], end paragraphs later).
        Word calls the file corrupt if the begin is tracked-deleted but the end is not, so drop the
        field-code runs untracked (they hold no visible text); the result text stays as plain runs."""
        depth, j = 0, idx[0]
        while j < len(self.paras) and (j in idx or depth > 0):
            for r in self.paras[j].xpath("./w:r[w:fldChar or w:instrText]", namespaces=NS):
                depth += {"begin": 1, "end": -1}.get(r.xpath("string(w:fldChar/@w:fldCharType)", namespaces=NS), 0)
                r.getparent().remove(r)
            j += 1

    def body_texts(self) -> list[str]:
        """Text of every paragraph before the References heading (where citations live)."""
        heading, idx = self.reference_block()
        end = heading if heading is not None else idx[0] if idx else len(self.paras)
        return [para_text(p) for p in self.paras[:end]]

    def apply(self, replacements: dict[int, str], additions: list[str], author: str, body_fn=None) -> tuple[bytes, int]:
        """replacements: {paragraph index: full new text}; additions: new entries appended to the block;
        body_fn(text) -> text rewrites citations in the paragraphs before the heading. Returns (docx, body paragraphs changed)."""
        ids = [int(x) for x in self.root.xpath("//@w:id", namespaces=NS) if x.isdigit()]
        tr = Tracker(author, max(ids, default=0) + 1)
        heading, idx = self.reference_block()
        if idx:
            self._unlink_fields(idx)
        for j in idx:  # Word numbering goes (untracked, it holds no text): the rewritten entries carry a typed [n]
            for n in self.paras[j].findall("w:pPr/w:numPr", NS):
                n.getparent().remove(n)
        body_changed = 0
        end = heading if heading is not None else idx[0] if idx else len(self.paras)  # same bound as body_texts()
        if body_fn:
            body_changed = sum(tr.rewrite_runs(p, body_fn) for p in self.paras[:end])
        for j, text in replacements.items():
            tr.replace_paragraph_text(self.paras[j], text)
        anchor = self.paras[idx[-1]] if idx else (self.paras[heading] if heading is not None else (self.paras[-1] if self.paras else None))
        template = self.paras[idx[-1]] if idx else None
        if additions and (self.block or {}).get("append"):  # no list in the document: a new section heading, tracked like the entries
            additions = ["**References**"] + additions
        for text in additions:
            new_p = tr.new_paragraph(text, template)
            if anchor is None:
                self.body.insert(0, new_p)
            else:
                anchor.addnext(new_p)
            anchor = new_p
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in self.zin.infolist():
                data = self.zin.read(info.filename)
                if info.filename == "word/document.xml":
                    data = etree.tostring(self.root, xml_declaration=True, encoding="UTF-8", standalone=True)
                zout.writestr(info, data)
        return out.getvalue(), body_changed


def apply_references(docx_bytes: bytes, items: list[dict], author: str = "esalab") -> bytes:
    """items: [{"text": "...", "replaces": "<substring of an existing entry>"?}, ...] (kept for the simple API)."""
    doc = Doc(docx_bytes)
    entries = doc.entries()
    repl, add = {}, []
    for it in items:
        target = next((e for e in entries if it.get("replaces") and it["replaces"] in e["text"]), None)
        if target:
            repl[target["index"]] = it["text"]
        else:
            add.append(it["text"])
    return doc.apply(repl, add, author)[0]
