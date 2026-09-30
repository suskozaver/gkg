// GKG on a Garmin watch: what every screen shares. Colours, fonts, drawing
// (every screen is drawn for 454x454 and scaled), and what is kept on the
// watch:
//
//   token, server     from linking: the watch's token and the server it came from
//   view              the last { rev, syncedAt, lists } from the server
//   outbox            ticks not yet confirmed by the server, oldest first
//
// A tick shows at once: it goes into the outbox and onto the stored view, and
// the outbox is sent at the next sync. The server's answer is taken as it
// comes, with whatever is still in the outbox laid over it again.

import Toybox.Application;
import Toybox.Attention;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.Math;
import Toybox.System;

module Gkg {
    const ACCENT = 0xF9B600;
    /** Garmin's blue: the other half of the mark, the ring and the last G of GKG. */
    const BLUE = 0x007CC3;
    const WHITE = 0xFFFFFF;
    const GREY = 0x9E9E9E;
    const DIM = 0x6B6B6B;
    const BOX = 0x1E1E1E;
    const BLACK = 0x000000;
    const INK = 0x1F1C12;
    const GREEN = 0x33B24A;

    const MAX_OUTBOX = 100;

    // ---- small things

    function str(v as Object?) as String {
        return v == null ? "" : v.toString();
    }

    function num(v as Object?) as Number {
        if (v instanceof Number) {
            return v;
        }
        if (v instanceof Long or v instanceof Float or v instanceof Double) {
            return (v as Long or Float or Double).toNumber();
        }
        return 0;
    }

    function vibe(ms as Number) as Void {
        if (Attention has :vibrate) {
            Attention.vibrate([new Attention.VibeProfile(60, ms)] as Array<Attention.VibeProfile>);
        }
    }

    // ---- the server: a setting, from Garmin Connect on the phone

    /**
     * The server as set, tidied: spaces and a trailing slash go, a bare host
     * name gets https:// in front of it, and http:// becomes https://, so the
     * token never travels in the clear. Empty when none is set.
     */
    function base() as String {
        var v = null;
        try {
            v = Properties.getValue("server");
        } catch (e) {
            v = null;
        }
        var s = "";
        var raw = str(v);
        for (var i = 0; i < raw.length(); i++) {
            var ch = raw.substring(i, i + 1) as String;
            if (!ch.equals(" ")) {
                s += ch;
            }
        }
        while (s.length() > 0 && s.substring(s.length() - 1, s.length()).equals("/")) {
            s = s.substring(0, s.length() - 1) as String;
        }
        if (s.equals("")) {
            return "";
        }
        var scheme = s.find("://");
        if (scheme == null) {
            s = "https://" + s;
        } else if (!s.substring(0, scheme).toLower().equals("https")) {
            s = "https" + s.substring(scheme, s.length());
        }
        return s;
    }

    function hasServer() as Boolean {
        return !base().equals("");
    }

    /** The server without https://, for the screen. */
    function host() as String {
        var b = base();
        var i = b.find("://");
        return i == null ? b : b.substring(i + 3, b.length()) as String;
    }

    /** The server this watch's token came from. */
    function linkedTo() as String {
        return str(Storage.getValue("server"));
    }

    /** Linked, but to another server than the one set now: the token is no good there. */
    function stale() as Boolean {
        return token() != null && !linkedTo().equals(base());
    }

    // ---- what is kept on the watch

    function token() as String? {
        return Storage.getValue("token") as String?;
    }

    /** The stored view, read once; Storage is only written. */
    var cache as Dictionary? = null;

    function view() as Dictionary {
        if (cache == null) {
            var v = Storage.getValue("view");
            cache = v instanceof Dictionary ? v as Dictionary : {} as Dictionary;
        }
        return cache as Dictionary;
    }

    /** Kept in memory at once; on the watch too when it fits (a very long list may not). */
    function keepView(v as Dictionary) as Void {
        cache = v;
        try {
            Storage.setValue("view", v);
        } catch (e) {
            Storage.deleteValue("view");
        }
    }

    function lists() as Array<Dictionary> {
        var l = view()["lists"];
        return l instanceof Array ? l as Array<Dictionary> : [] as Array<Dictionary>;
    }

    function rev() as String {
        return str(view()["rev"]);
    }

    function findList(id as String) as Dictionary? {
        var all = lists();
        for (var i = 0; i < all.size(); i++) {
            if (str(all[i]["id"]).equals(id)) {
                return all[i];
            }
        }
        return null;
    }

    function outbox() as Array<Dictionary> {
        var v = Storage.getValue("outbox");
        return v instanceof Array ? v as Array<Dictionary> : [] as Array<Dictionary>;
    }

    /** What the server sent, with the ticks it has not had yet laid over it. */
    function takeView(data as Dictionary) as Void {
        var v = { "rev" => str(data["rev"]), "syncedAt" => num(data["syncedAt"]), "lists" => data["lists"] } as Dictionary;
        overlay(v, outbox());
        keepView(v);
    }

    /** The first n changes went through. */
    function dropSent(n as Number) as Void {
        var box = outbox();
        Storage.setValue("outbox", n >= box.size() ? [] as Array<Dictionary> : box.slice(n, null));
    }

    /**
     * Tick or untick here: on the stored view now, into the outbox for the
     * server. A second change to the same item replaces the first.
     */
    function tick(listId as String, itemId as String, done as Boolean) as Void {
        var box = outbox();
        var out = [] as Array<Dictionary>;
        for (var i = 0; i < box.size(); i++) {
            var c = box[i];
            if (!(str(c["list"]).equals(listId) && str(c["item"]).equals(itemId))) {
                out.add(c);
            }
        }
        out.add({ "op" => "check", "list" => listId, "item" => itemId, "done" => done } as Dictionary);
        if (out.size() > MAX_OUTBOX) {
            out = out.slice(out.size() - MAX_OUTBOX, null);
        }
        Storage.setValue("outbox", out);
        var v = view();
        overlay(v, [out[out.size() - 1]] as Array<Dictionary>);
        keepView(v);
    }

    function overlay(v as Dictionary, changes as Array<Dictionary>) as Void {
        var ls = v["lists"];
        if (!(ls instanceof Array)) {
            return;
        }
        for (var k = 0; k < changes.size(); k++) {
            var c = changes[k];
            for (var i = 0; i < ls.size(); i++) {
                var l = ls[i] as Dictionary;
                if (!str(l["id"]).equals(str(c["list"])) || !(l["items"] instanceof Array)) {
                    continue;
                }
                var items = l["items"] as Array<Dictionary>;
                var open = 0;
                for (var j = 0; j < items.size(); j++) {
                    if (str(items[j]["id"]).equals(str(c["item"]))) {
                        items[j]["done"] = c["done"];
                    }
                    if (items[j]["done"] != true) {
                        open++;
                    }
                }
                l["open"] = open;
            }
        }
    }

    function forget() as Void {
        Storage.deleteValue("token");
        Storage.deleteValue("server");
        Storage.deleteValue("username");
        Storage.deleteValue("view");
        Storage.deleteValue("outbox");
        cache = null;
    }

    // ---- one screen size, scaled to the watch

    const REF = 454;
    var scale as Float = 1.0;

    function fit(dc as Graphics.Dc) as Void {
        var w = dc.getWidth();
        var h = dc.getHeight();
        scale = (w < h ? w : h).toFloat() / REF;
    }

    function s(v as Number) as Number {
        return scale == 1.0 ? v : (v * scale).toNumber();
    }

    function un(v as Number) as Number {
        return scale == 1.0 ? v : (v / scale).toNumber();
    }

    // ---- fonts: the system's scalable ones where the watch has them

    var fonts as Dictionary = {};

    function font(face as String, size as Number, fallback as Graphics.FontDefinition) as Graphics.FontType {
        var key = face + size;
        var f = fonts[key];
        if (f == null) {
            if (Graphics has :getVectorFont) {
                f = Graphics.getVectorFont({ :face => face, :size => size });
            }
            if (f == null) {
                f = fallback;
            }
            fonts[key] = f;
        }
        return f as Graphics.FontType;
    }

    function cond(size as Number) as Graphics.FontType {
        return font("RobotoCondensedBold", s(size), size >= 44 ? Graphics.FONT_MEDIUM : size >= 32 ? Graphics.FONT_SMALL : Graphics.FONT_XTINY);
    }

    function regular(size as Number) as Graphics.FontType {
        return font("RobotoCondensedRegular", s(size), size >= 32 ? Graphics.FONT_SMALL : Graphics.FONT_XTINY);
    }

    function digits(size as Number) as Graphics.FontType {
        return font("BionicBold", s(size), size >= 70 ? Graphics.FONT_NUMBER_MEDIUM : size >= 44 ? Graphics.FONT_NUMBER_MILD : Graphics.FONT_MEDIUM);
    }

    // ---- drawing

    function smooth(dc as Graphics.Dc) as Void {
        if (dc has :setAntiAlias) {
            dc.setAntiAlias(true);
        }
    }

    function text(dc as Graphics.Dc, x as Number, y as Number, f as Graphics.FontType, txt as String, color as Number, justify as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.drawText(s(x), s(y), f, txt, justify | Graphics.TEXT_JUSTIFY_VCENTER);
    }

    /** A ring along the bezel: `frac` of it, clockwise from the top. */
    function ring(dc as Graphics.Dc, frac as Float, color as Number, width as Number) as Void {
        var c = dc.getWidth() / 2;
        var pen = s(width);
        var r = c - pen / 2 - 1;
        dc.setPenWidth(pen);
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        if (frac >= 0.999) {
            dc.drawCircle(c, c, r);
        } else if (frac > 0.002) {
            var end = 90 - (360 * frac).toNumber();
            dc.drawArc(c, c, r, Graphics.ARC_CLOCKWISE, 90, end < 0 ? end + 360 : end);
        }
        dc.setPenWidth(1);
    }

    /** An arc along the bezel, clockwise from `start` degrees (0 = 3 o'clock, 90 = the top) for `sweep` degrees. */
    function arc(dc as Graphics.Dc, start as Number, sweep as Number, color as Number, width as Number) as Void {
        if (sweep <= 0) {
            return;
        }
        var c = dc.getWidth() / 2;
        var pen = s(width);
        dc.setPenWidth(pen);
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        var end = start - sweep;
        while (end < 0) {
            end += 360;
        }
        dc.drawArc(c, c, c - pen / 2 - 1, Graphics.ARC_CLOCKWISE, start, end);
        dc.setPenWidth(1);
    }

    /**
     * The brand ring: the right half blue, the left half yellow, like the mark.
     * `frac` of it, clockwise from the top: the blue half first, then the yellow.
     */
    function brandRing(dc as Graphics.Dc, frac as Float, width as Number) as Void {
        if (frac <= 0.002) {
            return;
        }
        var deg = frac >= 0.999 ? 360 : (360 * frac).toNumber();
        arc(dc, 90, deg < 180 ? deg : 180, BLUE, width);
        if (deg > 180) {
            arc(dc, 270, deg - 180, ACCENT, width);
        }
    }

    /** GKG as the brand writes it: GK yellow, the last G blue, centred on (px, py). */
    function brand(dc as Graphics.Dc, px as Number, py as Number, f as Graphics.FontType) as Void {
        var w1 = dc.getTextWidthInPixels("GK", f);
        var w2 = dc.getTextWidthInPixels("G", f);
        var x = s(px) - (w1 + w2) / 2;
        dc.setColor(ACCENT, Graphics.COLOR_TRANSPARENT);
        dc.drawText(x, s(py), f, "GK", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.setColor(BLUE, Graphics.COLOR_TRANSPARENT);
        dc.drawText(x + w1, s(py), f, "G", Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
    }

    /** A tick mark: two strokes, round-ended, in a box of `size` centred on (px, py). */
    function check(dc as Graphics.Dc, px as Number, py as Number, size as Number, color as Number, pen as Number) as Void {
        var x = s(px);
        var y = s(py);
        var h = s(size) / 2;
        var p = s(pen);
        if (p < 2) {
            p = 2;
        }
        var a = [x - h * 6 / 10, y + h * 2 / 100];
        var b = [x - h * 15 / 100, y + h * 45 / 100];
        var e = [x + h * 62 / 100, y - h * 45 / 100];
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        dc.setPenWidth(p);
        dc.drawLine(a[0], a[1], b[0], b[1]);
        dc.drawLine(b[0], b[1], e[0], e[1]);
        dc.fillCircle(a[0], a[1], p / 2);
        dc.fillCircle(b[0], b[1], p / 2);
        dc.fillCircle(e[0], e[1], p / 2);
        dc.setPenWidth(1);
    }

    /** The app's mark, as on the launcher icon: a disc, left half yellow and right half blue, with a tick. */
    function logo(dc as Graphics.Dc, px as Number, py as Number, pr as Number) as Void {
        var x = s(px);
        var y = s(py);
        var r = s(pr);
        dc.setColor(ACCENT, ACCENT);
        dc.fillCircle(x, y, r);
        dc.setClip(x, y - r - 1, r + 2, 2 * r + 3);
        dc.setColor(BLUE, BLUE);
        dc.fillCircle(x, y, r);
        dc.clearClip();
        check(dc, px, py, pr * 11 / 10, INK, pr * 22 / 100);
    }

    /** A box for an item: outlined when open, filled with a tick when done. */
    function box(dc as Graphics.Dc, px as Number, py as Number, size as Number, done as Boolean, on as Boolean) as Void {
        var x = s(px - size / 2);
        var y = s(py - size / 2);
        var z = s(size);
        var r = s(7);
        if (done) {
            dc.setColor(on ? ACCENT : DIM, on ? ACCENT : DIM);
            dc.fillRoundedRectangle(x, y, z, z, r);
            check(dc, px, py, size * 8 / 10, on ? INK : BLACK, 5);
        } else {
            dc.setColor(on ? WHITE : GREY, Graphics.COLOR_TRANSPARENT);
            dc.setPenWidth(s(3) < 2 ? 2 : s(3));
            dc.drawRoundedRectangle(x, y, z, z, r);
            dc.setPenWidth(1);
        }
    }

    /** Half the width of the round screen at height y (reference pixels). */
    function halfWidth(y as Number, w as Number) as Number {
        var r = w / 2;
        var d = y - r;
        if (d < 0) {
            d = -d;
        }
        if (d >= r) {
            return 0;
        }
        return Math.sqrt(r * r - d * d).toNumber();
    }

    /** Words into lines no wider than `width` real pixels. Newlines are kept. */
    function wrap(dc as Graphics.Dc, txt as String, f as Graphics.FontType, width as Number) as Array<String> {
        var out = [] as Array<String>;
        var paras = split(txt, "\n");
        for (var p = 0; p < paras.size(); p++) {
            var words = split(paras[p], " ");
            var line = "";
            for (var i = 0; i < words.size(); i++) {
                var wd = words[i];
                var next = line.equals("") ? wd : line + " " + wd;
                if (dc.getTextWidthInPixels(next, f) <= width || line.equals("")) {
                    line = next;
                } else {
                    out.add(line);
                    line = wd;
                }
            }
            out.add(line);
        }
        return out;
    }

    function split(txt as String, sep as String) as Array<String> {
        var out = [] as Array<String>;
        var rest = txt;
        while (true) {
            var i = rest.find(sep);
            if (i == null) {
                out.add(rest);
                return out;
            }
            out.add(rest.substring(0, i) as String);
            rest = rest.substring(i + sep.length(), rest.length()) as String;
        }
        return out;
    }
}

// Scrolling text: a line that does not fit moves slowly to its end and back,
// with a pause at each end. Fonts never shrink for it.
module Marquee {
    const SPEED = 55;
    const PAUSE = 1300;

    var started as Dictionary = {};
    /** Set while drawing when something on screen is moving, so the view keeps redrawing. */
    var active as Boolean = false;

    // The box is [x, y, width, height] on the 454 reference screen: one
    // argument, because watches on API 3 allow a method nine arguments.
    function draw(dc as Graphics.Dc, key as String, s as String, f as Graphics.FontType, color as Number, box as Array<Number>, justify as Number) as Void {
        dc.setColor(color, Graphics.COLOR_TRANSPARENT);
        var x = Gkg.s(box[0]);
        var y = Gkg.s(box[1]);
        var w = Gkg.s(box[2]);
        var h = Gkg.s(box[3]);
        var tw = dc.getTextWidthInPixels(s, f);
        if (tw <= w) {
            var tx = justify == Graphics.TEXT_JUSTIFY_CENTER ? x + w / 2 : justify == Graphics.TEXT_JUSTIFY_RIGHT ? x + w : x;
            dc.drawText(tx, y, f, s, justify | Graphics.TEXT_JUSTIFY_VCENTER);
            return;
        }
        active = true;
        var now = System.getTimer();
        var st = started[key] as Array?;
        if (st == null || !(st[0] as String).equals(s)) {
            st = [s, now];
            started[key] = st;
        }
        var over = tw - w;
        var move = over * 1000 / SPEED;
        var period = 2 * PAUSE + 2 * move;
        var t = (now - (st[1] as Number)) % period;
        var off = 0;
        if (t < PAUSE) {
            off = 0;
        } else if (t < PAUSE + move) {
            off = (t - PAUSE) * over / move;
        } else if (t < 2 * PAUSE + move) {
            off = over;
        } else {
            off = over - (t - 2 * PAUSE - move) * over / move;
        }
        dc.setClip(x, y - h / 2, w, h);
        dc.drawText(x - off, y, f, s, Graphics.TEXT_JUSTIFY_LEFT | Graphics.TEXT_JUSTIFY_VCENTER);
        dc.clearClip();
    }

    function reset(key as String) as Void {
        started.remove(key);
    }
}
