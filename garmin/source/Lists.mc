// The first screen when more than one list is on the watch: the lists, the
// chosen one in the middle. START or a tap opens it.

import Toybox.Graphics;
import Toybox.Lang;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;

/** Where rows sit: the chosen one at CENTRE, but near the top the list starts under the header. */
module Rows {
    const CENTRE = 262;
    const TOP = 124;

    function shift(sel as Number, rowH as Number) as Number {
        var y = sel * rowH + rowH / 2;
        var sh = CENTRE - y;
        var first = TOP + rowH / 2;
        return sh > first - rowH / 2 ? first - rowH / 2 : sh;
    }

    /** The row at y (reference pixels), or -1. */
    function at(y as Number, n as Number, rowH as Number, shift as Number) as Number {
        if (y < TOP - 10) {
            return -1;
        }
        var i = ((y - shift) / rowH).toNumber();
        return i >= 0 && i < n ? i : -1;
    }

    /** The header over the rows: a title and one line under it. */
    function header(dc as Graphics.Dc, title as String, sub as String, subColor as Number) as Void {
        var c = Gkg.REF / 2;
        dc.setColor(Gkg.BLACK, Gkg.BLACK);
        dc.fillRectangle(0, 0, dc.getWidth(), Gkg.s(TOP - 8));
        Marquee.draw(dc, "title", title, Gkg.cond(32), Gkg.ACCENT, [c - 120, 60, 240, 40], Graphics.TEXT_JUSTIFY_CENTER);
        Marquee.draw(dc, "sub", sub, Gkg.cond(24), subColor, [c - 140, 96, 280, 30], Graphics.TEXT_JUSTIFY_CENTER);
    }

    /** Nothing to show: the mark in a ring (which runs while syncing) and two lines. */
    function empty(dc as Graphics.Dc, line1 as String, line2 as String) as Void {
        var c = Gkg.REF / 2;
        var server = getApp().server;
        if (server.state == :busy) {
            Gkg.ring(dc, 1.0f, Gkg.BOX, 12);
            Gkg.ring(dc, (System.getTimer() % 1500).toFloat() / 1500, Gkg.ACCENT, 12);
            Marquee.active = true;
        } else {
            Gkg.ring(dc, 1.0f, server.trouble() ? Gkg.DIM : Gkg.ACCENT, 12);
        }
        Gkg.logo(dc, c, 140, 56);
        Gkg.text(dc, c, 240, Gkg.cond(40), line1, Gkg.WHITE, Graphics.TEXT_JUSTIFY_CENTER);
        Marquee.draw(dc, "empty", line2, Gkg.cond(28), Gkg.GREY, [c - 170, 290, 340, 36], Graphics.TEXT_JUSTIFY_CENTER);
        var status = server.line();
        if (!status.equals("")) {
            Gkg.text(dc, c, 390, Gkg.cond(24), status, server.trouble() ? Gkg.DIM : Gkg.GREEN, Graphics.TEXT_JUSTIFY_CENTER);
        }
    }

    /** The status line for a header: trouble first, else the given line. */
    function sub(normal as String) as String {
        var server = getApp().server;
        return server.state == :busy || server.trouble() || Gkg.outbox().size() > 0 ? server.line() : normal;
    }
}

/**
 * While a list screen is open the server is asked again now and then, so a
 * change made in Keep turns up without leaving the app.
 */
class Poll {
    var asked as Number = 0;

    function initialize() {
    }

    function start() as Void {
        asked = System.getTimer();
        getApp().server.refresh();
    }

    function tick() as Void {
        var now = System.getTimer();
        if (now < asked) {
            asked = now;
        }
        if (now - asked >= 60000) {
            asked = now;
            getApp().server.refresh();
        }
    }
}

class ListsView extends WatchUi.View {
    var sel as Number = 0;
    var selId as String = "";
    var list as Array<Dictionary> = [] as Array<Dictionary>;
    var gen as Number = -1;
    var timer as Timer.Timer?;
    var moving as Boolean = false;
    var poll as Poll = new Poll();
    var shift as Number = 0;
    const ROW = 84;

    function initialize() {
        View.initialize();
    }

    function onShow() as Void {
        getApp().depth = 0;
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
        list = Gkg.lists();
        sel = 0;
        for (var i = 0; i < list.size(); i++) {
            if (Gkg.str(list[i]["id"]).equals(selId)) {
                sel = i;
            }
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

    function scroll(d as Number) as Void {
        var n = list.size();
        if (n == 0) {
            return;
        }
        var to = sel + d;
        to = to < 0 ? 0 : to > n - 1 ? n - 1 : to;
        if (to != sel) {
            move(to - sel);
        }
    }

    function move(d as Number) as Void {
        if (list.size() == 0) {
            return;
        }
        sel = (sel + d + list.size()) % list.size();
        selId = Gkg.str(list[sel]["id"]);
        Marquee.reset("row");
        WatchUi.requestUpdate();
    }

    function open(i as Number) as Void {
        if (i < 0 || i >= list.size()) {
            return;
        }
        sel = i;
        selId = Gkg.str(list[i]["id"]);
        getApp().depth = 1;
        var v = new ItemsView(selId, false);
        WatchUi.pushView(v, new ItemsDelegate(v), WatchUi.SLIDE_LEFT);
    }

    function tap(y as Number) as Void {
        open(Rows.at(Gkg.un(y), list.size(), ROW, shift));
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        Gkg.fit(dc);
        var w = Gkg.REF;
        var c = w / 2;
        dc.setColor(Gkg.WHITE, Gkg.BLACK);
        dc.clear();
        Gkg.smooth(dc);
        Marquee.active = false;

        if (list.size() == 0) {
            Rows.empty(dc, "No lists", "Pick them on " + Gkg.host());
            moving = Marquee.active;
            return;
        }
        shift = Rows.shift(sel, ROW);
        for (var i = 0; i < list.size(); i++) {
            var ry = i * ROW + ROW / 2 + shift;
            if (ry < 70 || ry > w + 50) {
                continue;
            }
            var l = list[i];
            var on = i == sel;
            var half = Gkg.halfWidth(ry, w) - 26;
            if (half < 60) {
                continue;
            }
            if (on) {
                dc.setColor(Gkg.BOX, Gkg.BOX);
                dc.fillRoundedRectangle(Gkg.s(c - half - 10), Gkg.s(ry - ROW / 2 + 4), Gkg.s(2 * half + 20), Gkg.s(ROW - 8), Gkg.s(16));
                dc.setColor(Gkg.ACCENT, Gkg.ACCENT);
                dc.fillRoundedRectangle(Gkg.s(c - half - 10), Gkg.s(ry - ROW / 2 + 16), Gkg.s(6), Gkg.s(ROW - 32), Gkg.s(3));
            }
            var name = Gkg.str(l["title"]);
            var f = Gkg.cond(36);
            if (on) {
                Marquee.draw(dc, "row", name, f, Gkg.WHITE, [c - half + 4, ry - 14, 2 * half - 8, 42], Graphics.TEXT_JUSTIFY_CENTER);
            } else {
                dc.setClip(Gkg.s(c - half), Gkg.s(ry - 36), Gkg.s(2 * half), Gkg.s(44));
                var tw = Gkg.un(dc.getTextWidthInPixels(name, f));
                Gkg.text(dc, tw <= 2 * half ? c : c - half, ry - 14, f, name, Gkg.GREY, tw <= 2 * half ? Graphics.TEXT_JUSTIFY_CENTER : Graphics.TEXT_JUSTIFY_LEFT);
                dc.clearClip();
            }
            var sub = "";
            if (Gkg.str(l["kind"]).equals("note")) {
                sub = "Note";
            } else {
                var open = Gkg.num(l["open"]);
                sub = open == 0 ? "All done" : open + " open";
            }
            if (l["pinned"] == true) {
                sub = "Pinned · " + sub;
            }
            Gkg.text(dc, c, ry + 20, Gkg.cond(24), sub, on ? Gkg.ACCENT : Gkg.DIM, Graphics.TEXT_JUSTIFY_CENTER);
        }
        Rows.header(dc, "GKG", Rows.sub(list.size() == 1 ? "1 list" : list.size() + " lists"), getApp().server.trouble() ? Gkg.DIM : Gkg.GREY);
        moving = Marquee.active;
    }
}

class ListsDelegate extends WatchUi.BehaviorDelegate {
    var view as ListsView;

    function initialize(v as ListsView) {
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
        view.open(view.sel);
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
}
