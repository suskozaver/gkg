"""GKeepClient against a real gkeepapi tree, built locally (no network)."""
from app.keep import GKeepClient


def test_notes_check_add_on_local_tree():
    c = GKeepClient()
    k = c._keep
    lst = k.createList("Trgovina", [("Mleko", False), ("Kruh", True)])
    lst.pinned = True
    k.createNote("Ideas", "some text")
    notes = {n["title"]: n for n in c.notes()}
    t = notes["Trgovina"]
    assert t["kind"] == "list" and t["pinned"] and [i["text"] for i in t["items"]] == ["Mleko", "Kruh"]
    assert [i["checked"] for i in t["items"]] == [False, True]
    assert notes["Ideas"]["kind"] == "note" and notes["Ideas"]["text"] == "some text"

    milk = t["items"][0]["id"]
    assert c.set_checked(lst.id, milk, True)
    assert c.set_checked(lst.id, milk, True)  # again: no harm
    assert not c.set_checked(lst.id, "nope", True)
    assert not c.set_checked(notes["Ideas"]["id"], milk, True)
    assert c.add_item(lst.id, "Jajca")
    items = next(n for n in c.notes() if n["id"] == lst.id)["items"]
    assert [(i["text"], i["checked"]) for i in items] == [("Mleko", True), ("Kruh", True), ("Jajca", False)]
    # The dump is plain JSON (it is sealed before it is written).
    import json

    json.dumps(c.dump())
