// One list: its items, the chosen one in the middle. START (or a tap on an
// item) ticks it, or unticks a ticked one; the cursor then moves to the next
// item, so a list is ticked off from the top down. The tick shows at once and
// goes to the server a moment later (Server.soon). A plain note shows its
// text, scrolled with UP and DOWN.

import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Timer;
import Toybox.WatchUi;

class ItemsView extends WatchUi.View {
    var listId as String;
    /** The first screen (one list on the watch), not opened from the lists. */
    var isRoot as Boolean;
    var list as Dictionary? = null;
    var items as Array<Dictionary> = [] as Array<Dictionary>;
    var lines as Array<String>? = null;
    var sel as Number = 0;
    var selId as String = "";
    var gen as Number = -1;
    var timer as Timer.Timer?;
    var moving as Boolean = false;
    var poll as Poll = new Poll();
    var shift as Number = 0;
    const ROW = 72;
    const LINE = 40;

    function initialize(id as String, root as Boolean) {
        View.initialize();
        listId = id;
        isRoot = root;
    }

    function onShow() as Void {
        getApp().depth = isRoot ? 0 : 1;
        load();
        timer = new Timer.Timer();
        (timer as Timer.Timer).start(method(:onTick), 100, true);
        poll.start();
    }

    function onHide() as Void {
        if (timer != null) {
            (timer as Timer.Timer).stop();
            timer = null;
        }
    }

    private function load() as Void {
        gen = getApp().gen;
        list = Gkg.findList(listId);
        if (isRoot && list == null) {
            // The one list on the watch is another one now.
            var all = Gkg.lists();
            if (all.size() == 1) {
                list = all[0];
                listId = Gkg.str(all[0]["id"]);
                selId = "";
            }
        }
        items = [] as Array<Dictionary>;
        lines = null;
        if (list != null && (list as Dictionary)["items"] instanceof Array) {
            items = (list as Dictionary)["items"] as Array<Dictionary>;
        }
        if (isNote()) {
            return;
        }
        // The chosen item stays chosen when the list moves around it.
        var found = false;
        for (var i = 0; i < items.size(); i++) {
            if (Gkg.str(items[i]["id"]).equals(selId)) {
                sel = i;
                found = true;
            }
        }
        if (!found && sel >= items.size()) {
            sel = items.size() > 0 ? items.size() - 1 : 0;
        }
    }

    function onTick() as Void {
        poll.tick();
        if (gen != getApp().gen) {
            load();
            WatchUi.requestUpdate();
        } else if (moving) {
            WatchUi.requestUpdate();
        }
    }

    function isNote() as Boolean {
        return list != null && Gkg.str((list as Dictionary)["kind"]).equals("note");
    }

    function scroll(d as Number) as Void {
        var n = items.size();
        if (isNote() || n == 0) {
            move(d > 0 ? 1 : -1);
            return;
        }
        var to = sel + d;
        to = to < 0 ? 0 : to > n - 1 ? n - 1 : to;
        if (to != sel) {
            move(to - sel);
        }
    }

    function move(d as Number) as Void {
        var n = isNote() ? (lines == null ? 0 : (lines as Array).size()) : items.size();
        if (n == 0) {
            return;
        }
        if (isNote()) {
            // Text scrolls and stops at its ends.
            sel += d * 3;
            if (sel > n - 1) {
                sel = n - 1;
            }
            if (sel < 0) {
                sel = 0;
            }
        } else {
            sel = (sel + d + n) % n;
            selId = Gkg.str(items[sel]["id"]);
        }
        Marquee.reset("row");
        WatchUi.requestUpdate();
    }

    /** Tick or untick item i, then move on to the next one. */
    function toggle(i as Number) as Void {
        if (isNote() || i < 0 || i >= items.size()) {
            return;
        }
        var it = items[i];
        var done = it["done"] != true;
        Gkg.tick(listId, Gkg.str(it["id"]), done);
        Gkg.vibe(done ? 40 : 25);
        sel = i + 1 < items.size() ? i + 1 : i;
        selId = Gkg.str(items[sel]["id"]);
        Marquee.reset("row");
        getApp().changed();
        getApp().server.soon();
    }

    function tap(y as Number) as Void {
        if (isNote()) {
            return;
        }
        toggle(Rows.at(Gkg.un(y), items.size(), ROW, shift));
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        Gkg.fit(dc);
        var w = Gkg.REF;
        dc.setColor(Gkg.WHITE, Gkg.BLACK);
        dc.clear();
        Gkg.smooth(dc);
        Marquee.active = false;

        if (list == null) {
            Rows.empty(dc, "Not here", "This list is no longer on the watch");
            moving = Marquee.active;
            return;
        }
        var l = list as Dictionary;
        var title = Gkg.str(l["title"]);
        if (isNote()) {
            drawNote(dc, w, l);
            Rows.header(dc, title, Rows.sub("Note"), getApp().server.trouble() ? Gkg.DIM : Gkg.GREY);
            moving = Marquee.active;
            return;
        }
        if (items.size() == 0) {
            Rows.empty(dc, "All done", title);
            moving = Marquee.active;
            return;
        }
        drawItems(dc, w);
        var open = Gkg.num(l["open"]);
        var normal = open == 0 ? "All done" : open + " of " + items.size() + " open";
        Rows.header(dc, title, Rows.sub(normal), getApp().server.trouble() ? Gkg.DIM : Gkg.GREY);
        moving = Marquee.active;
    }

    private function drawItems(dc as Graphics.Dc, w as Number) as Void {
        var c = w / 2;
        shift = Rows.shift(sel, ROW);
        for (var i = 0; i < items.size(); i++) {
            var ry = i * ROW + ROW / 2 + shift;
            if (ry < 70 || ry > w + 40) {
                continue;
            }
            var it = items[i];
            var on = i == sel;
            var done = it["done"] == true;
            var half = Gkg.halfWidth(ry, w) - 22;
            if (half < 70) {
                continue;
            }
            if (on) {
                dc.setColor(Gkg.BOX, Gkg.BOX);
                dc.fillRoundedRectangle(Gkg.s(c - half - 8), Gkg.s(ry - ROW / 2 + 4), Gkg.s(2 * half + 16), Gkg.s(ROW - 8), Gkg.s(16));
            }
            var indent = it["sub"] == true ? 28 : 0;
            var bx = c - half + 22 + indent;
            Gkg.box(dc, bx, ry, 30, done, on);
            var tx = bx + 30;
            var tw = c + half - 8 - tx;
            var f = Gkg.cond(32);
            var color = done ? Gkg.DIM : on ? Gkg.WHITE : Gkg.GREY;
            var name = Gkg.str(it["text"]);
            if (on) {
                Marquee.draw(dc, "row", name, f, color, [tx, ry, tw, 42], Graphics.TEXT_JUSTIFY_LEFT);
            } else {
                dc.setClip(Gkg.s(tx), Gkg.s(ry - 22), Gkg.s(tw), Gkg.s(44));
                Gkg.text(dc, tx, ry, f, name, color, Graphics.TEXT_JUSTIFY_LEFT);
                dc.clearClip();
            }
            if (done) {
                // Struck through, as in Keep.
                var len = Gkg.un(dc.getTextWidthInPixels(name, f));
                if (len > tw) {
                    len = tw;
                }
                dc.setColor(Gkg.DIM, Graphics.COLOR_TRANSPARENT);
                dc.setPenWidth(Gkg.s(2) < 1 ? 1 : Gkg.s(2));
                dc.drawLine(Gkg.s(tx), Gkg.s(ry + 2), Gkg.s(tx + len), Gkg.s(ry + 2));
                dc.setPenWidth(1);
            }
        }
    }

    private function drawNote(dc as Graphics.Dc, w as Number, l as Dictionary) as Void {
        var c = w / 2;
        var f = Gkg.regular(30);
        if (lines == null) {
            lines = Gkg.wrap(dc, Gkg.str(l["text"]), f, Gkg.s(300));
        }
        var ls = lines as Array<String>;
        // `sel` is the first line shown.
        for (var i = sel; i < ls.size(); i++) {
            var y = Rows.TOP + 20 + (i - sel) * LINE;
            if (y > w - 64) {
                break;
            }
            Gkg.text(dc, c, y, f, ls[i], Gkg.WHITE, Graphics.TEXT_JUSTIFY_CENTER);
        }
    }
}

class ItemsDelegate extends WatchUi.BehaviorDelegate {
    var view as ItemsView;

    function initialize(v as ItemsView) {
        BehaviorDelegate.initialize();
        view = v;
    }

    function onNextPage() as Boolean {
        view.move(1);
        return true;
    }

    function onPreviousPage() as Boolean {
        view.move(-1);
        return true;
    }

    function onSelect() as Boolean {
        view.toggle(view.sel);
        return true;
    }

    // A swipe moves three rows and stops at the ends; the buttons move one and wrap.
    function onSwipe(e as WatchUi.SwipeEvent) as Boolean {
        var d = e.getDirection();
        if (d == WatchUi.SWIPE_UP) {
            view.scroll(3);
            return true;
        }
        if (d == WatchUi.SWIPE_DOWN) {
            view.scroll(-3);
            return true;
        }
        return false;
    }

    function onTap(e as WatchUi.ClickEvent) as Boolean {
        view.tap(e.getCoordinates()[1]);
        return true;
    }

    function onMenu() as Boolean {
        openMenu();
        return true;
    }

    function onBack() as Boolean {
        if (view.isRoot) {
            return false;
        }
        getApp().depth = 0;
        WatchUi.popView(WatchUi.SLIDE_RIGHT);
        return true;
    }
}
