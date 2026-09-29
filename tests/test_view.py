from app import view as v


def lst(id, title="", items=(), labels=(), pinned=False, archived=False, trashed=False, updated=0, kind="list", text=""):
    return {"id": id, "kind": kind, "title": title, "pinned": pinned, "archived": archived, "trashed": trashed,
            "labels": list(labels), "updated": updated, "items": list(items), "text": text}


def item(id, text, checked=False, indented=False):
    return {"id": id, "text": text, "checked": checked, "indented": indented}


NOTES = [
    lst("a", "Trgovina", [item("a1", "Mleko"), item("a2", "Kruh", True), item("a3", "  ")], labels=["garmin"], updated=5),
    lst("b", "Hribi", [item("b1", "Čelada")], pinned=True, updated=1),
    lst("c", "Old", archived=True, updated=9),
    lst("d", "Gone", trashed=True, labels=["garmin"]),
    lst("e", "Ideas", kind="note", text="some text", updated=7),
]


def test_defaults_every_live_list_pinned_first():
    out = v.watch_view(NOTES, {})
    assert [l["id"] for l in out["lists"]] == ["b", "a"]
    a = out["lists"][1]
    assert [i["text"] for i in a["items"]] == ["Mleko", "Kruh"]  # blank item dropped, done last
    assert a["open"] == 1 and a["items"][1]["done"] is True


def test_labels_and_ids_pick_archived_too():
    out = v.watch_view(NOTES, {"labels": ["garmin"], "notes": ["c"]})
    assert [l["id"] for l in out["lists"]] == ["c", "a"]  # trashed never, archived when asked by id; newest first


def test_hide_checked_and_order():
    out = v.watch_view(NOTES, {"checked": "hide", "order": "title"})
    assert [l["title"] for l in out["lists"]] == ["Hribi", "Trgovina"]
    assert [i["text"] for i in out["lists"][1]["items"]] == ["Mleko"]
    assert [l["id"] for l in v.watch_view(NOTES, {"order": "updated"})["lists"]] == ["a", "b"]


def test_text_notes():
    out = v.watch_view(NOTES, {"textNotes": True})
    e = next(l for l in out["lists"] if l["id"] == "e")
    assert e["kind"] == "note" and e["text"] == "some text" and "items" not in e


def test_untitled_and_clipping():
    n = [lst("x", "", [item("x1", "first item " * 20)])]
    out = v.watch_view(n, {})
    assert out["lists"][0]["title"] == ("first item " * 20).strip()[: v.MAX_TITLE]
    assert len(out["lists"][0]["items"][0]["text"]) == v.MAX_TEXT
    assert v.title_of(lst("y")) == "Untitled"


def test_clean_settings():
    s = v.clean_settings({"labels": ["b", "a", "a", 3], "checked": "x", "order": "title", "templates": "Milk\n\n Milk \nBread\n", "textNotes": "yes"})
    assert s == {"labels": ["a", "b"], "notes": [], "textNotes": False, "checked": "bottom", "order": "title", "templates": ["Milk", "Bread"]}


def test_rev_changes_with_content():
    a = v.watch_view(NOTES, {})
    b = v.watch_view(NOTES, {"checked": "hide"})
    assert v.rev_of(a) == v.rev_of(v.watch_view(NOTES, {})) != v.rev_of(b)


def test_clean_changes():
    c = v.clean_changes([
        {"op": "check", "list": "a", "item": "a1", "done": True},
        {"op": "check", "list": "a", "item": "a1", "done": "yes"},
        {"op": "add", "list": "a", "text": "  Jajca "},
        {"op": "add", "list": "", "text": "x"},
        {"op": "delete", "list": "a"},
        "junk",
    ])
    assert c == [{"op": "check", "list": "a", "item": "a1", "done": True}, {"op": "add", "list": "a", "text": "Jajca"}]
    assert v.clean_changes(None) == []
