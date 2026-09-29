# GKG for Garmin

A Connect IQ watch app for the fēnix 8 AMOLED 47/51 mm (`fenix847mm`, 454×454,
touch and buttons). Its own app id (`manifest.xml`), in the Connect IQ store as a
**beta** app: only the developer account sees it.

What it does:
- Talks to the GKG server set in **Garmin Connect › GKG › Settings › Server** (default
  `https://gkg.wtf.si`; a bare host name gets `https://`). Before a code it checks that
  a GKG server answers there (`/api/health`), and the code screen names the server.
  The token is kept with the server it came from: change the setting and the watch forgets
  the token, the lists and any waiting ticks, and asks the new server for a code.
- Links with a six-digit code, valid for three minutes, typed on the server's Home page.
- Shows the lists picked on gkg.wtf.si › Watch. One list: the app opens straight into
  it. More: the lists first, each with how many items are open.
- Ticks an item, or unticks a ticked one, with START or a tap; the cursor moves on to
  the next item. The tick shows at once and goes to the server 1.5 s later, so a few
  quick ticks go in one request. Without the phone they wait on the watch (the header
  says how many) and go at the next sync.
- A plain note (when turned on on the web) shows its text, UP and DOWN scroll it.
- Syncs when a list screen opens and every minute while it stays open; the server
  itself syncs with Keep first when its last sync is older than 30 seconds.
- Hold UP for the menu: Sync now, Unlink watch.

| Button | Does |
|---|---|
| UP / DOWN | Previous / next (wraps round) |
| Swipe up / down | Three rows on, stopping at the ends |
| START, or a tap on the row | Tick / untick (lists: open) |
| BACK, or a swipe right | Back to the lists, or out |
| Hold UP | Menu |

## Code

`source/Gkg.mc` (colours, storage, drawing, scaling from 454 — ported from Eat Train
Feel's Etf.mc), `Server.mc` (the three calls), `Pair.mc`, `Lists.mc` (with `Rows`, the
layout both list screens share, and `Poll`), `Items.mc`, `App.mc` (which screen comes
first, the menu). The server's half is `app/main.py`; the API is in the README at the
root.

## Building

The deploy watcher builds it with the developer key in `C:\garmin-keys`:

    echo build  > .garmin-build-request    ->  garmin\bin\GKG.prg  (simulator, USB)
    echo export > .garmin-build-request    ->  garmin\bin\GKG.iq   (the store)

Upload `GKG.iq` in the Connect IQ developer dashboard as a beta app; install it on the
phone from its page in the Connect IQ app. Store and sideloaded builds are the same app
only while they are signed with the same key.

Simulator: `scripts\sim.bat` builds if needed, starts the simulator and loads the app.
