import Toybox.Application;
import Toybox.Lang;
import Toybox.WatchUi;

class GkgApp extends Application.AppBase {
    var server as Server;
    /** Goes up whenever the stored lists change, so open screens know to read them again. */
    var gen as Number = 0;
    /** What the first screen is: :pair, :lists (more than one list) or :items (exactly one). */
    var root as Symbol = :pair;
    /** Screens opened on top of the first one. */
    var depth as Number = 0;

    function initialize() {
        AppBase.initialize();
        server = new Server();
    }

    function getInitialView() as [WatchUi.Views] or [WatchUi.Views, WatchUi.InputDelegates] {
        if (Gkg.stale()) {
            Gkg.forget();
        }
        if (Gkg.token() == null) {
            root = :pair;
            var p = new PairView();
            return [p, new PairDelegate(p)];
        }
        return homeView();
    }

    /**
     * The server was changed in Garmin Connect. Linked to another one: that
     * token, the lists and the waiting ticks go, and the watch asks the new
     * server for a code. Still on the code screen: a code from the new one.
     */
    function onSettingsChanged() as Void {
        if (Gkg.stale()) {
            Gkg.forget();
            showPairing();
        } else if (root == :pair) {
            showPairing();
        }
        WatchUi.requestUpdate();
    }

    /**
     * The stored lists changed. When the number of lists crosses one, the
     * first screen changes with it: one list opens straight into its items.
     */
    function changed() as Void {
        gen++;
        if (depth == 0 && root != :pair && root != kind()) {
            var v = homeView();
            WatchUi.switchToView(v[0], v[1], WatchUi.SLIDE_IMMEDIATE);
        }
        WatchUi.requestUpdate();
    }

    function kind() as Symbol {
        return Gkg.lists().size() == 1 ? :items : :lists;
    }

    function homeView() as [WatchUi.Views, WatchUi.InputDelegates] {
        depth = 0;
        root = kind();
        if (root == :items) {
            var only = Gkg.lists()[0];
            var iv = new ItemsView(Gkg.str(only["id"]), true);
            return [iv, new ItemsDelegate(iv)];
        }
        var lv = new ListsView();
        return [lv, new ListsDelegate(lv)];
    }
}

function getApp() as GkgApp {
    return Application.getApp() as GkgApp;
}

function showHome() as Void {
    var v = getApp().homeView();
    WatchUi.switchToView(v[0], v[1], WatchUi.SLIDE_LEFT);
}

function showPairing() as Void {
    getApp().root = :pair;
    getApp().depth = 0;
    var v = new PairView();
    WatchUi.switchToView(v, new PairDelegate(v), WatchUi.SLIDE_IMMEDIATE);
}

/** The menu on every list screen (hold UP): sync, unlink. */
function openMenu() as Void {
    var m = new WatchUi.Menu2({ :title => "GKG" });
    m.addItem(new WatchUi.MenuItem("Sync now", getApp().server.line(), :sync, null));
    m.addItem(new WatchUi.MenuItem("Unlink watch", Gkg.username().equals("") ? null : "Linked to " + Gkg.username(), :unlink, null));
    WatchUi.pushView(m, new MenuDelegate(), WatchUi.SLIDE_UP);
}

class MenuDelegate extends WatchUi.Menu2InputDelegate {
    function initialize() {
        Menu2InputDelegate.initialize();
    }

    function onSelect(item as WatchUi.MenuItem) as Void {
        var id = item.getId();
        WatchUi.popView(WatchUi.SLIDE_DOWN);
        if (id == :sync) {
            getApp().server.refresh();
        } else if (id == :unlink) {
            // The web still lists it until unlinked there; this watch forgets its token.
            Gkg.forget();
            showPairing();
        }
    }
}
