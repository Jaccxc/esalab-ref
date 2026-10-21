from esalab.order import cited_sequence, final_numbers, parse_group, plan, rewrite


def test_parse_groups():
    assert parse_group("[3]–[5]") == [3, 4, 5]
    assert parse_group("[3-5]") == [3, 4, 5]
    assert parse_group("[2, +1]") == [2, "+1"]
    assert parse_group("[ 7 ]") == [7]
    assert parse_group("[1, 3–5]") == [1, 3, 4, 5]


def test_plan_renumbers_by_first_appearance_and_places_new_entries():
    seq = cited_sequence(["as shown [2] and [+1]", "then [1], [3]–[5] and [2]"])
    assert seq == [2, "+1", 1, 3, 4, 5]
    p = plan(6, seq, [1, 2])
    assert p["order"] == [2, "+1", 1, 3, 4, 5, 6, "+2"]  # uncited old 6 then uncited new +2 at the end
    assert p["renumber"] == {1: 3, 2: 1, 3: 4, 4: 5, 5: 6, 6: 7} and p["placeholders"] == {"+1": 2, "+2": 8}
    assert p["uncited"] == [6, "+2"] and p["unknown"] == [] and p["ok"] is False
    assert rewrite("as shown [2] and [+1], then [1], [3]–[5] and [6].", final_numbers(p)) == "as shown [1] and [2], then [3], [4]–[6] and [7]."


def test_plan_is_ok_when_nothing_moves_and_aliases_duplicates():
    p = plan(3, [1, 2, 3], [])
    assert p["ok"] and p["renumber"] == {} and p["placeholders"] == {}
    p = plan(3, [1, "+1", 2], [], aliases={"+1": 3})  # +1 is a title already in the list as [3]
    assert p["order"] == [1, 3, 2] and p["placeholders"] == {"+1": 2}
    assert rewrite("[1] [+1] [2] [9]", final_numbers(p)) == "[1] [2] [3] [9]"  # unknown [9] untouched


def test_lookup_results_are_cached_in_sqlite(monkeypatch, tmp_path):
    from esalab import db, lookup as lk
    monkeypatch.setattr(db, "DB", tmp_path / "t.db")
    calls = []
    monkeypatch.setattr(lk, "lookup_live", lambda q, hint=None: calls.append(q) or {"title": q, "match": "exact" if "hit" in q else "none", "candidates": []})
    assert lk.lookup("A hit paper")["match"] == "exact" and lk.lookup("a HIT paper ")["cached"] is True  # normalised key
    assert lk.lookup("missing")["match"] == "none" and lk.lookup("missing")["match"] == "none"
    assert calls == ["A hit paper", "missing", "missing"]  # misses are re-searched, hits are not


def test_unknown_numbers_are_kept_but_known_neighbours_still_move():
    p = plan(3, cited_sequence(["[2], [54] then [1, 54] and [+9]"]), [1])
    assert p["unknown"] == [54, "+9"] and p["order"] == [2, 1, 3, "+1"]
    assert rewrite("[2], [54] then [1, 54] and [+9]", final_numbers(p)) == "[1], [54] then [2], [54] and [+9]"
