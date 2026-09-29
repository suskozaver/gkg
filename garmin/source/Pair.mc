// Linking: the watch first checks that the server set in Garmin Connect is
// a GKG server, then asks it for a six-digit code, shows it with a ring that
// runs out in three minutes, and asks every few seconds whether it was typed
// on that server's Home page. When it was, the watch gets its token, once,
// and remembers which server gave it. (Eat Train Feel's Pair.mc, in GKG's
// colours.)

import Toybox.Application;
import Toybox.Communications;
import Toybox.Graphics;
import Toybox.Lang;
import Toybox.System;
import Toybox.Timer;
import Toybox.WatchUi;

class PairView extends WatchUi.View {
    var code as String? = null;
    var secret as String? = null;
    var total as Number = 180;
    var endsAt as Number = 0;
    /** :unset (no server set), :asking, :showing, :offline, :noserver (no GKG there), :expired, :busy (too many codes) */
    var state as Symbol = :asking;
    var renewals as Number = 0;
    var waiting as Boolean = false;
    var timer as Timer.Timer?;
    var ticks as Number = 0;

    function initialize() {
        View.initialize();
    }

    function onShow() as Void {
        timer = new Timer.Timer();
        (timer as Timer.Timer).start(method(:onTick), 1000, true);
        if (code == null) {
            ask();
        }
    }

    function onHide() as Void {
        if (timer != null) {
            (timer as Timer.Timer).stop();
            timer = null;
        }
    }

    /** Is there a GKG server at the address set? Then a code. */
    function ask() as Void {
        code = null;
        if (!Gkg.hasServer()) {
            // Nothing to ask yet: the server is set on the phone, and the app hears when it is.
            state = :unset;
            WatchUi.requestUpdate();
            return;
        }
        state = :asking;
        WatchUi.requestUpdate();
        Communications.makeWebRequest(Gkg.base() + "/api/health", null, {
            :method => Communications.HTTP_REQUEST_METHOD_GET,
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
        }, method(:onHealth));
    }

    function onHealth(rc as Number, data as Dictionary or String or Null) as Void {
        if (rc == 200 && data instanceof Dictionary && data["ok"] == true && data["version"] != null) {
            getCode();
            return;
        }
        // No answer at all is the phone; any other answer is the address.
        state = rc < 0 && rc != -400 && rc != -402 && rc != -1001 ? :offline : :noserver;
        WatchUi.requestUpdate();
    }

    function getCode() as Void {
        Communications.makeWebRequest(Gkg.base() + "/api/watch/pair", {}, {
            :method => Communications.HTTP_REQUEST_METHOD_POST,
            :headers => { "Content-Type" => Communications.REQUEST_CONTENT_TYPE_JSON },
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
        }, method(:onCode));
    }

    function onCode(rc as Number, data as Dictionary or String or Null) as Void {
        if (rc == 200 && data instanceof Dictionary && data["code"] != null) {
            code = Gkg.str(data["code"]);
            secret = Gkg.str(data["secret"]);
            total = Gkg.num(data["expiresIn"]);
            if (total <= 0) {
                total = 180;
            }
            endsAt = System.getTimer() + total * 1000;
            state = :showing;
        } else {
            state = rc == 429 ? :busy : :offline;
        }
        WatchUi.requestUpdate();
    }

    function onTick() as Void {
        ticks++;
        if (state == :showing) {
            if (System.getTimer() >= endsAt) {
                // A fresh code by itself a few times, then only when asked.
                if (renewals < 4) {
                    renewals++;
                    ask();
                } else {
                    state = :expired;
                }
            } else if (ticks % 3 == 0 && !waiting) {
                waiting = true;
                Communications.makeWebRequest(Gkg.base() + "/api/watch/status", { "secret" => Gkg.str(secret) }, {
                    :method => Communications.HTTP_REQUEST_METHOD_POST,
                    :headers => { "Content-Type" => Communications.REQUEST_CONTENT_TYPE_JSON },
                    :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
                }, method(:onStatus));
            }
        }
        WatchUi.requestUpdate();
    }

    function onStatus(rc as Number, data as Dictionary or String or Null) as Void {
        waiting = false;
        if (rc == 200 && data instanceof Dictionary && Gkg.str(data["status"]).equals("linked") && data["token"] != null) {
            Application.Storage.setValue("token", Gkg.str(data["token"]));
            Application.Storage.setValue("server", Gkg.base());
            Application.Storage.setValue("username", Gkg.str(data["username"]));
            Gkg.vibe(300);
            showHome();
            getApp().server.refresh();
        } else if (rc == 404) {
            // Gone at the server (a restart, or it expired): a new one.
            ask();
        }
    }

    function retry() as Void {
        if (state != :asking && state != :showing) {
            renewals = 0;
            ask();
        }
    }

    function onUpdate(dc as Graphics.Dc) as Void {
        Gkg.fit(dc);
        var c = Gkg.REF / 2;
        dc.setColor(Gkg.WHITE, Gkg.BLACK);
        dc.clear();
        Gkg.smooth(dc);

        if (state == :showing && code != null) {
            var left = (endsAt - System.getTimer()) / 1000;
            if (left < 0) {
                left = 0;
            }
            var s = code as String;
            Gkg.ring(dc, 1.0f, Gkg.BOX, 12);
            Gkg.ring(dc, left.toFloat() / total, Gkg.ACCENT, 12);
            Gkg.logo(dc, c, 80, 34);
            Gkg.text(dc, c, 150, Gkg.cond(30), "Link this watch", Gkg.WHITE, Graphics.TEXT_JUSTIFY_CENTER);
            Gkg.text(dc, c, 228, Gkg.digits(96), s.substring(0, 3) + " " + s.substring(3, 6), Gkg.WHITE, Graphics.TEXT_JUSTIFY_CENTER);
            Marquee.active = false;
            Marquee.draw(dc, "host", Gkg.host() + " › Home", Gkg.cond(28), Gkg.GREY, [c - 160, 304, 320, 36], Graphics.TEXT_JUSTIFY_CENTER);
            Gkg.text(dc, c, 346, Gkg.cond(28), (left / 60) + ":" + (left % 60).format("%02d"), Gkg.DIM, Graphics.TEXT_JUSTIFY_CENTER);
            return;
        }
        Gkg.ring(dc, 1.0f, state == :asking || state == :unset ? Gkg.ACCENT : Gkg.DIM, 12);
        Gkg.logo(dc, c, 130, 58);
        Gkg.text(dc, c, 228, Gkg.cond(44), "GKG", Gkg.WHITE, Graphics.TEXT_JUSTIFY_CENTER);
        var line1 = "Getting a code…";
        var line2 = "";
        if (state == :unset) {
            line1 = "Set your server";
            line2 = "on the phone";
        } else if (state == :offline) {
            line1 = "No connection";
            line2 = "Is the phone nearby?";
        } else if (state == :noserver) {
            line1 = "No GKG server at";
            line2 = Gkg.host();
        } else if (state == :expired) {
            line1 = "The code ran out";
        } else if (state == :busy) {
            line1 = "Too many codes";
            line2 = "Try again in an hour";
        }
        Gkg.text(dc, c, 282, Gkg.cond(32), line1, Gkg.GREY, Graphics.TEXT_JUSTIFY_CENTER);
        if (!line2.equals("")) {
            Marquee.draw(dc, "line2", line2, Gkg.cond(28), Gkg.DIM, [c - 160, 318, 320, 36], Graphics.TEXT_JUSTIFY_CENTER);
        }
        if (state == :noserver || state == :unset) {
            Gkg.text(dc, c, 362, Gkg.cond(24), "Connect IQ app", Gkg.GREY, Graphics.TEXT_JUSTIFY_CENTER);
            Gkg.text(dc, c, 394, Gkg.cond(24), "GKG › Settings › Server", Gkg.GREY, Graphics.TEXT_JUSTIFY_CENTER);
        } else if (state != :asking) {
            Gkg.text(dc, c, 370, Gkg.cond(28), "START for a new code", Gkg.ACCENT, Graphics.TEXT_JUSTIFY_CENTER);
        }
    }
}

class PairDelegate extends WatchUi.BehaviorDelegate {
    var view as PairView;

    function initialize(v as PairView) {
        BehaviorDelegate.initialize();
        view = v;
    }

    function onSelect() as Boolean {
        view.retry();
        return true;
    }
}
