// Talking to the GKG server (Gkg.base), through the phone. One request at a time: ticks
// waiting on the watch go first (the answer is the fresh lists), otherwise
// the lists, with the rev the watch has so an unchanged answer is tiny.

import Toybox.Application;
import Toybox.Communications;
import Toybox.Lang;
import Toybox.System;
import Toybox.Time;
import Toybox.Timer;
import Toybox.WatchUi;

class Server {
    /** :idle, :busy, :ok, :offline, :keep (the server could not reach Keep), :error */
    var state as Symbol = :idle;
    var busy as Boolean = false;
    /** Asked again while busy: one more round when this one ends. */
    var again as Boolean = false;
    /** When the last sync went through, in seconds (0: not yet since the app started). */
    var syncedAt as Number = 0;
    /** How many outbox entries the request in flight carries. */
    private var sending as Number = 0;
    private var later as Timer.Timer?;

    function initialize() {
    }

    function authHeaders(json as Boolean) as Dictionary {
        var h = { "Authorization" => "Bearer " + Gkg.str(Gkg.token()) } as Dictionary;
        if (json) {
            h["Content-Type"] = Communications.REQUEST_CONTENT_TYPE_JSON;
        }
        return h;
    }

    function refresh() as Void {
        if (Gkg.token() == null) {
            return;
        }
        if (busy) {
            again = true;
            return;
        }
        busy = true;
        state = :busy;
        WatchUi.requestUpdate();
        var box = Gkg.outbox();
        if (box.size() > 0) {
            sending = box.size();
            Communications.makeWebRequest(Gkg.base() + "/api/watch/changes", { "changes" => box }, {
                :method => Communications.HTTP_REQUEST_METHOD_POST,
                :headers => authHeaders(true),
                :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
            }, method(:onChanges));
            return;
        }
        Communications.makeWebRequest(Gkg.base() + "/api/watch/lists", { "rev" => Gkg.rev() }, {
            :method => Communications.HTTP_REQUEST_METHOD_GET,
            :headers => authHeaders(false),
            :responseType => Communications.HTTP_RESPONSE_CONTENT_TYPE_JSON
        }, method(:onLists));
    }

    /** A sync a moment from now, so a few quick ticks go in one request. */
    function soon() as Void {
        if (later != null) {
            (later as Timer.Timer).stop();
        }
        later = new Timer.Timer();
        (later as Timer.Timer).start(method(:refresh), 1500, false);
    }

    function onChanges(code as Number, data as Dictionary or String or Null) as Void {
        if (code == 200 && data instanceof Dictionary && data["lists"] instanceof Array) {
            Gkg.dropSent(sending);
            take(data);
            done();
            return;
        }
        fail(code);
    }

    function onLists(code as Number, data as Dictionary or String or Null) as Void {
        if (code == 200 && data instanceof Dictionary) {
            if (data["username"] != null) {
                Storage.setValue("username", Gkg.str(data["username"]));
            }
            if (data["lists"] instanceof Array) {
                take(data);
            }
            done();
            if (Gkg.str(data["keep"]).equals("error")) {
                state = :keep;
            }
            return;
        }
        fail(code);
    }

    private function take(data as Dictionary) as Void {
        Gkg.takeView(data);
        getApp().changed();
    }

    private function done() as Void {
        busy = false;
        state = :ok;
        syncedAt = Time.now().value();
        WatchUi.requestUpdate();
        if (again) {
            again = false;
            refresh();
        }
    }

    private function fail(code as Number) as Void {
        busy = false;
        again = false;
        if (code == 401) {
            // Unlinked on the web: back to a code.
            Gkg.forget();
            state = :idle;
            showPairing();
            return;
        }
        state = code < 0 ? :offline : code == 503 ? :keep : :error;
        WatchUi.requestUpdate();
    }

    /** One line for the screen: syncing, synced when, or what is wrong. */
    function line() as String {
        if (state == :busy) {
            return "Syncing…";
        }
        if (state == :offline) {
            return "Phone not connected";
        }
        if (state == :keep) {
            return "Keep not reachable";
        }
        if (state == :error) {
            return "Could not sync";
        }
        var box = Gkg.outbox().size();
        if (box > 0) {
            return box == 1 ? "1 change waiting" : box + " changes waiting";
        }
        if (syncedAt == 0) {
            return "";
        }
        var mins = (Time.now().value() - syncedAt) / 60;
        return mins < 1 ? "Synced just now" : mins < 60 ? "Synced " + mins + " min ago" : "Synced " + (mins / 60) + " h ago";
    }

    function trouble() as Boolean {
        return state == :offline || state == :keep || state == :error;
    }
}
