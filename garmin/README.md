# GKG for Garmin

A Connect IQ watch app for 74 round Garmin watches with buttons: the AMOLED ones (fēnix 8 and 9, epix 2, Forerunner 165 to 970, MARQ 2,
Descent, D2, Approach S70) and the MIP ones down to API 3.3 (fēnix 5 Plus to 9 Pro
Solar, Enduro 3, Forerunner 245 Music to 955, the first MARQ). Every screen is drawn for
454×454 and scaled down, to 218 px on the smallest. Left out: watches with 128 KB for
an app, the touch-first Venu and vívoactive, and Instinct with its second window. On a
watch with a touch screen a tap ticks and a swipe scrolls; the buttons work on all.
Two app ids: `manifest.xml` is the **public** app in the Connect IQ
store, `manifest-beta.xml` the **beta** one (only the developer account sees it; a beta
app cannot be published). They are otherwise the same file. To a watch a new id is a new
app: it starts empty and is linked again with a code.

What it does:
- Talks to the GKG server set in the app's settings on the phone (Connect IQ app: My Device ›
  My Apps › GKG › Settings; Garmin Connect: the watch › Connect IQ Apps › GKG › Settings).
  The setting starts empty and the watch says so ("Set your server"); a bare host name
  gets `https://`. Before a code it checks that
  a GKG server answers there (`/api/health`), and the code screen names the server.
  The token is kept with the server it came from: change the setting and the watch forgets
  the token, the lists and any waiting ticks, and asks the new server for a code.
- Links with a six-digit code, valid for three minutes, typed on the server's Home page.
- Shows the lists picked on the server's Watch page. One list: the app opens straight into
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

`source/Gkg.mc` (colours, storage, drawing, scaling from 454), `Server.mc` (the three calls), `Pair.mc`, `Lists.mc` (with `Rows`, the
layout both list screens share, and `Poll`), `Items.mc`, `App.mc` (which screen comes
first, the menu). The server's half is `app/main.py`; the API is in the README at the
root.

## Building

With the Connect IQ SDK and your own developer key (`openssl genrsa` / `pkcs8 -outform DER`,
as the SDK's documentation shows):

    # one watch, for the simulator or a USB install (GARMIN/Apps)
    monkeyc -f garmin/monkey.jungle -d fenix847mm -y developer_key.der -o GKG.prg -w
    monkeydo GKG.prg fenix847mm

    # the store package, every watch in the manifest
    monkeyc -e -r -f garmin/monkey.jungle -y developer_key.der -o GKG.iq -w

`monkey-beta.jungle` builds the same app under the beta id. Store and sideloaded builds
are the same app only while they are signed with the same key.
