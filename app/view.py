"""
What the watch is shown, and the settings that decide it. Pure: plain notes
in (as `keep.KeepClient.notes()` gives them), plain data out; tested in
tests/test_view.py.

A note here:
    { id, kind: "list"|"note", title, pinned, archived, trashed, labels: [name],
      updated: epoch seconds, items: [{ id, text, checked, indented }], text }

Settings (`settings.json`):
    labels     notes with any of these labels are shown
    notes      these notes are shown, whatever their labels
               (both empty: every list that is not archived)
    textNotes  plain notes too, read-only; otherwise lists only
    checked    "bottom" (after the rest) or "hide"
    order      "pinned" (pinned first, then newest), "updated", "title"
    templates  quick items to add from the watch
"""
from __future__ import annotations

import hashlib
import json
import re

MAX_LISTS = 20
MAX_ITEMS = 80
MAX_TITLE = 40
MAX_TEXT = 80
MAX_NOTE_TEXT = 1500
MAX_TEMPLATES = 30
MAX_TEMPLATE = 60
MAX_ADD = 200

DEFAULTS = {"labels": [], "notes": [], "textNotes": False, "checked": "bottom", "order": "pinned", "templates": []}


def _clip(v, n: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def clean_settings(raw) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULTS)
    out["labels"] = sorted({_clip(x, 100) for x in raw.get("labels", []) if isinstance(x, str) and x.strip()})[:100]
    out["notes"] = list(dict.fromkeys(str(x)[:100] for x in raw.get("notes", []) if isinstance(x, str) and x))[:100]
    out["textNotes"] = raw.get("textNotes") is True
    out["checked"] = raw.get("checked") if raw.get("checked") in ("bottom", "hide") else "bottom"
    out["order"] = raw.get("order") if raw.get("order") in ("pinned", "updated", "title") else "pinned"
    tpl = raw.get("templates", [])
    if isinstance(tpl, str):
        tpl = tpl.splitlines()
    out["templates"] = list(dict.fromkeys(t for t in (_clip(x, MAX_TEMPLATE) for x in tpl if isinstance(x, str)) if t))[:MAX_TEMPLATES]
    return out


def chosen(notes: list[dict], settings: dict) -> list[dict]:
    """The notes the settings pick, in the settings' order, before any clipping."""
    s = clean_settings(settings)
    live = [n for n in notes if not n.get("trashed")]
    kinds = ("list", "note") if s["textNotes"] else ("list",)
    live = [n for n in live if n.get("kind") in kinds]
    if s["labels"] or s["notes"]:
        want_labels, want_ids = set(s["labels"]), set(s["notes"])
        picked = [n for n in live if n["id"] in want_ids or want_labels & set(n.get("labels", []))]
    else:
        picked = [n for n in live if not n.get("archived")]
    if s["order"] == "title":
        picked.sort(key=lambda n: (title_of(n).casefold(), -n.get("updated", 0)))
    elif s["order"] == "updated":
        picked.sort(key=lambda n: -n.get("updated", 0))
    else:
        picked.sort(key=lambda n: (not n.get("pinned"), -n.get("updated", 0)))
    return picked


def title_of(n: dict) -> str:
    t = _clip(n.get("title"), MAX_TITLE)
    if t:
        return t
    first = next((i.get("text") for i in n.get("items", []) if _clip(i.get("text"), 1)), None) or n.get("text")
    return _clip(first, MAX_TITLE) or "Untitled"


def watch_view(notes: list[dict], settings: dict) -> dict:
    s = clean_settings(settings)
    lists = []
    for n in chosen(notes, s)[:MAX_LISTS]:
        entry = {"id": n["id"], "title": title_of(n), "kind": n["kind"], "pinned": bool(n.get("pinned"))}
        if n["kind"] == "list":
            items = [i for i in n.get("items", []) if _clip(i.get("text"), 1)]
            open_items = [i for i in items if not i.get("checked")]
            done_items = [] if s["checked"] == "hide" else [i for i in items if i.get("checked")]
            entry["items"] = [
                {"id": i["id"], "text": _clip(i.get("text"), MAX_TEXT), "done": bool(i.get("checked")), **({"sub": True} if i.get("indented") else {})}
                for i in (open_items + done_items)[:MAX_ITEMS]
            ]
            entry["open"] = len(open_items)
        else:
            entry["text"] = str(n.get("text") or "")[:MAX_NOTE_TEXT]
        lists.append(entry)
    return {"lists": lists, "templates": s["templates"]}


def rev_of(view: dict) -> str:
    return hashlib.sha256(json.dumps(view, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def clean_changes(raw) -> list[dict]:
    """Changes the watch sends: ticking an item, or adding one. Anything else is dropped."""
    out = []
    for c in raw if isinstance(raw, list) else []:
        if not isinstance(c, dict):
            continue
        lst = str(c.get("list") or "")[:100]
        if not lst:
            continue
        if c.get("op") == "check" and c.get("item") and isinstance(c.get("done"), bool):
            out.append({"op": "check", "list": lst, "item": str(c["item"])[:100], "done": c["done"]})
        elif c.get("op") == "add" and _clip(c.get("text"), MAX_ADD):
            out.append({"op": "add", "list": lst, "text": _clip(c.get("text"), MAX_ADD)})
        if len(out) >= 50:
            break
    return out


def allowed_changes(changes: list[dict], shown: dict) -> list[dict]:
    """Only changes to what the watch was given: items of the lists in `shown` (a watch view)."""
    items = {l["id"]: {i["id"] for i in l.get("items", [])} for l in shown.get("lists", []) if l.get("kind") == "list"}
    out = []
    for c in changes:
        if c["op"] == "check" and c["item"] in items.get(c["list"], ()):
            out.append(c)
        elif c["op"] == "add" and c["list"] in items:
            out.append(c)
    return out
