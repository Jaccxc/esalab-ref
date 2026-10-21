import io
import zipfile

from lxml import etree

from esalab.docx_track import NS, apply_references, para_text, w
from tests.make_fixture import build


def _doc():
    buf = io.BytesIO()
    build(buf)
    return buf.getvalue()


def _xml(b):
    return etree.fromstring(zipfile.ZipFile(io.BytesIO(b)).read("word/document.xml"))


def test_append_and_replace_are_tracked():
    out = apply_references(_doc(), [
        {"text": "Vaswani A. Attention is all you need. *NeurIPS* 2017.", "replaces": "transformers"},
        {"text": "He K. Deep residual learning. *CVPR* 2016; 770-778."},
    ], author="tester")
    root = _xml(out)
    paras = root.findall("w:body/w:p", NS)
    texts = [para_text(p) for p in paras]
    # replaced entry: old runs are <w:del> with delText, new text in <w:ins>; stays in place
    old = paras[3]
    assert old.xpath("./w:del/w:r/w:delText", namespaces=NS)
    assert "Attention is all you need" in "".join(old.xpath("./w:ins//w:t/text()", namespaces=NS))
    # appended entry lands after "2. Another old entry." and before the "Appendix" heading
    assert texts[4] == "[2] Another old entry." and "Deep residual" in texts[5] and texts[6] == "Appendix"
    new = paras[5]
    assert new.find("w:pPr/w:rPr/w:ins", NS) is not None  # paragraph mark tracked too
    assert new.xpath("./w:ins/w:r[w:rPr/w:i]/w:t/text()", namespaces=NS) == ["CVPR"]
    ids = root.xpath("//w:ins/@w:id | //w:del/@w:id", namespaces=NS)
    assert len(ids) == len(set(ids))
    assert all(a == "tester" for a in root.xpath("//w:ins/@w:author", namespaces=NS))
    assert "Appendix text." in texts  # untouched content survives


def test_no_heading_appends_at_end(monkeypatch):
    import tests.make_fixture as mf
    monkeypatch.setattr(mf, "DOC", mf.DOC.replace("References", "Stuff"))  # zip is deflated, so patch the source
    root = _xml(apply_references(_doc(), [{"text": "X"}]))
    assert para_text(root.findall("w:body/w:p", NS)[-1]) == "X"


def test_endnote_field_is_unlinked_before_tracked_delete(monkeypatch):
    """EndNote wraps the list in one field: begin in [1], end paragraphs later. Word rejects a file where
    only the begin is inside <w:del>, so the field-code runs must be dropped before the replacement."""
    import io
    import zipfile

    from lxml import etree

    import tests.make_fixture as mf
    from esalab.docx_track import NS, Doc

    fld = lambda t: f'<w:r><w:fldChar w:fldCharType="{t}"/></w:r>'  # noqa: E731
    body = (
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>References</w:t></w:r></w:p>'
        f'<w:p>{fld("begin")}<w:r><w:instrText> ADDIN EN.REFLIST </w:instrText></w:r>{fld("separate")}<w:r><w:t>[1] Old one.</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>[2] Old two.</w:t></w:r></w:p>'
        f'<w:p>{fld("end")}</w:p>'
        f'<w:p>{fld("begin")}<w:r><w:instrText> SEQ Fig </w:instrText></w:r>{fld("separate")}<w:r><w:t>Fig. 9 kept</w:t></w:r>{fld("end")}</w:p>'
    )
    monkeypatch.setattr(mf, "DOC", mf.DOC.split("<w:body>")[0] + "<w:body>" + body + "<w:sectPr/></w:body></w:document>")
    buf = io.BytesIO()
    mf.build(buf)
    out, _ = Doc(buf.getvalue()).apply({1: "[1] New one."}, [], "t")
    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(out)).read("word/document.xml"))
    paras = root.findall("w:body/w:p", NS)
    assert not paras[1].xpath(".//w:fldChar | .//w:instrText", namespaces=NS) and not paras[3].xpath(".//w:fldChar", namespaces=NS)
    assert paras[1].xpath("./w:del/w:r/w:delText/text()", namespaces=NS) == ["Old"]  # word diff: only the changed word is tracked
    assert len(paras[4].xpath(".//w:fldChar", namespaces=NS)) == 3  # a later, unrelated field is untouched


def test_rewrite_spans_runs_of_different_formatting():
    from esalab.docx_track import Tracker
    from esalab.order import rewrite
    p = etree.fromstring(
        '<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:r><w:t>see [1</w:t></w:r>'
        '<w:r><w:rPr><w:b/></w:rPr><w:t>7</w:t></w:r><w:r><w:t>]</w:t></w:r><w:r><w:rPr><w:lang w:val="x"/></w:rPr><w:t>–[</w:t></w:r>'
        '<w:r><w:t>19]. Radar [20], [21] end.</w:t></w:r></w:p>')
    doc = Tracker("tester", 1)
    assert doc.rewrite_runs(p, lambda t: rewrite(t, {17: 16, 18: 17, 19: 18, 20: 19, 21: 20})) is True
    assert para_text(p) == "see [16]–[18]. Radar [19], [20] end."
    before = "".join(e.text or "" for e in p.iter() if e.tag == w("delText") or (e.tag == w("t") and e.getparent().getparent().tag != w("ins")))
    assert before == "see [17]–[19]. Radar [20], [21] end."  # deleted + untouched text in document order = the original
    assert p.xpath("./w:del/w:r/w:rPr/w:b", namespaces=NS)  # the deleted bold "7" keeps its formatting
    assert doc.rewrite_runs(p, lambda t: t) is False


def test_replace_is_a_word_diff():
    from esalab.docx_track import Tracker
    p = etree.fromstring('<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:r><w:t>[1]</w:t></w:r><w:r><w:tab/><w:t>A. Smith, "Title," Front Physiol., vol. 13, 200</w:t></w:r></w:p>')
    Tracker("tester", 1).replace_paragraph_text(p, '[1]\tA. Smith, "Title," *Front. Physiol.*, vol. 13, Jul. 2022.')
    assert p.xpath("./w:del/w:r/w:delText/text()", namespaces=NS) == ["Front", "Physiol.,", "200"]
    assert p.xpath("./w:ins/w:r/w:t/text()", namespaces=NS) == ["Front.", "Physiol.", ",", "Jul. 2022."]
    assert p.xpath("./w:ins/w:r[w:rPr/w:i]/w:t/text()", namespaces=NS) == ["Front.", "Physiol."]
    assert p.xpath("./w:r/w:t/text()", namespaces=NS) == ["[1]", 'A. Smith, "Title," ', " ", " vol. 13, "]  # untouched text keeps its runs
    assert p.xpath("./w:r/w:tab", namespaces=NS)
    # nothing in common: whole delete + insert, as before
    q = etree.fromstring('<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:r><w:t>completely different words here</w:t></w:r></w:p>')
    Tracker("tester", 1).replace_paragraph_text(q, "B. Jones, Other, 2001.")
    assert q.xpath("./w:del/w:r/w:delText/text()", namespaces=NS) == ["completely different words here"] and not q.xpath("./w:r", namespaces=NS)


def test_marked_text_merges_split_italic_runs():
    from esalab.docx_track import para_marked_text
    p = etree.fromstring('<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:r><w:t xml:space="preserve">A, "T," </w:t></w:r>'
                         '<w:r><w:rPr><w:i/></w:rPr><w:t>IEEE</w:t></w:r><w:r><w:t xml:space="preserve"> </w:t></w:r><w:r><w:rPr><w:i/></w:rPr><w:t>Trans. Biomed. Eng.</w:t></w:r><w:r><w:t>, 2023.</w:t></w:r></w:p>')
    assert para_marked_text(p) == 'A, "T," *IEEE Trans. Biomed. Eng.*, 2023.'
    from esalab.docx_track import norm_marks
    assert norm_marks("x,* Public Health, *vol.") == "x, *Public Health*, vol."
    assert norm_marks("*Proc*. *IEEE CIBCB*") == "*Proc*. *IEEE CIBCB*"  # a dot between spans is not a space: untouched
