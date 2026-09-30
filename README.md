# GKG — Keep lists on your Garmin watch

Your Google Keep lists on a Garmin watch: read them and tick items off from your
wrist. GKG is two parts:

- **the watch app**, from the Connect IQ store, and
- **the GKG server**, this code, which **you run yourself** (Docker). It signs in to
  Google Keep for you, keeps your notes encrypted, and gives the watch only the lists
  you picked.

```
watch ──(Bluetooth)──> phone ──(HTTPS)──> your GKG server ──> Google Keep
```

The watch never talks to Google, and nothing goes to the developer: see
[PRIVACY.md](PRIVACY.md). GKG is not affiliated with, endorsed by or sponsored by
Google or Garmin.

## Why a server of your own

Google's Keep API is for Workspace administrators only; a personal @gmail.com account
has none. The server uses [gkeepapi](https://github.com/kiwiz/gkeepapi), an unofficial
client that signs in the way an Android device does, with a **master token**. Two
things follow:

- it can stop working when Google changes something, until gkeepapi catches up;
- the master token opens your **whole Google account**, not only Keep. That is why the
  server is yours: the token never leaves a machine you control, and it is stored
  only encrypted (see Security).

## Running the server

You need a machine with Docker, a domain name pointing at it, and **HTTPS with a valid
certificate** in front of it (Caddy, Nginx Proxy Manager, Traefik…): the watch cannot
talk to a server without one. It must be reachable from the internet, since the watch
reaches it through your phone.

```bash
git clone https://github.com/suskozaver/gkg.git
cd gkg
cp .env.example .env         # then fill it in: the commands for the two keys are in the file
docker compose up -d --build
docker compose logs gkg      # on the first start: the link to create your account
```

`.env`:

| Variable | |
|---|---|
| `GKG_ORIGIN` | the address the server is reached at, e.g. `https://gkg.example.com` |
| `GKG_SESSION_SECRET` | signs the web sign-in; without it every restart signs you out |
| `GKG_DATA_KEY` | the key the Keep token and the cached notes are encrypted with. **Keep a copy somewhere safe** (a password manager): without it the stored token cannot be read and Keep has to be connected again |
| `GKG_SYNC_SECONDS` | how often the server syncs with Keep on its own (default 120) |
| `GKG_BIND` | where port 8791 is published: `127.0.0.1` (default) or `0.0.0.0` |
| `GKG_TRUSTED_PROXIES` | the proxy's addresses, whose `X-Real-IP` is believed (default: private networks) |
| `TZ` | time zone for dates on the web pages (default UTC) |

The container publishes port **8791** on `127.0.0.1` only (set `GKG_BIND=0.0.0.0` when
the proxy runs elsewhere, and keep 8791 closed to the internet). With Caddy on the same
machine, for example:

```
gkg.example.com {
	reverse_proxy localhost:8791 {
		header_up X-Real-IP {remote_host}
	}
}
```

The proxy must set `X-Real-IP` to the client's address (Nginx Proxy Manager does), and the
server believes it only from the addresses in `GKG_TRUSTED_PROXIES` (private networks by
default). The rate limits on sign-in and linking go by that address.

Then, on your server's web pages:

1. **Setup link** from the log: create the account (the only one; there is no sign-up).
2. **Keep**: connect your Google account. The page walks you through it: sign in at
   `accounts.google.com/EmbeddedSetup`, copy the `oauth_token` cookie, paste it. The
   server exchanges it for a master token at once and forgets the cookie. Using a
   separate Google account and sharing the lists with it limits what the token opens.
3. **Watch**: pick the lists the watch shows (by label or one by one), their order, and
   whether ticked items sit at the bottom or are hidden.

Updating: `git pull && docker compose up -d --build`. Backing up: the Docker volume
`gkg_gkg_data` and, separately, `GKG_DATA_KEY`.

## The watch

1. Install **GKG** from the Connect IQ store.
2. Open GKG's settings on the phone: in the **Connect IQ** app, My Device › My Apps ›
   GKG › **Settings**; or in **Garmin Connect**, your watch › Connect IQ Apps › GKG ›
   **Settings**. Set **Server** to your server's address, e.g. `https://gkg.example.com`.
3. Open GKG on the watch. It checks that a GKG server answers there and shows a
   six-digit code; type it on your server's **Home › Link a watch** within three minutes.

On the watch: one list opens straight into its items; more show the lists first.
START or a tap ticks an item (or unticks it) and moves on to the next; UP/DOWN or a
swipe scroll; hold UP for **Sync now** and **Unlink watch**. Ticks show at once and go
to the server through the phone; without the phone they wait on the watch. More in
[garmin/README.md](garmin/README.md).

## Security

- **Master token**: sealed with `GKG_DATA_KEY` (Fernet: AES-128-CBC + HMAC) in
  `keep.json`; the notes cached between restarts (`keep-state.bin`) are sealed too.
  The key lives only in `.env`, so the volume or a backup of it is useless without it.
  The server has to be able to decrypt, since it syncs on its own: whoever gets into
  the running container gets the token. **Disconnect** on the Keep page deletes both;
  to revoke the token itself, remove the device in your Google account's security
  settings.
- **Account**: one, no sign-up. scrypt password (at most two computed at once), a
  session cookie signed with `GKG_SESSION_SECRET` (HttpOnly, SameSite=Lax, Secure on
  https), 30 days; the server refuses to start with a placeholder or short secret.
  Changing the password signs out every other browser; linked watches stay linked
  (unlink them on Home if a session may have been stolen). 5 wrong passwords in 15
  minutes lock sign-in from that address for 15 minutes.
- **Linking a watch**: a code lives three minutes and only the signed-in owner can use
  it; 5 wrong codes in a day lock linking for 24 hours. Asking for codes is limited per
  address. The watch's token is 256 random bits and the server keeps only its SHA-256.
  At most 5 watches: linking a sixth unlinks the oldest.
- **What a watch token opens**: only the watch API, and in it only the lists picked on
  the Watch page: a tick for anything else is refused. **Unlink** revokes a token at
  once; a watch not heard from in 90 days is unlinked by itself. The watch app sends the
  token only to the server it was linked with, and only over https.
- **Web**: every form post must carry this site's Origin (or Referer); responses carry a
  strict Content-Security-Policy (no scripts), `X-Frame-Options: DENY`, `nosniff` and
  `Referrer-Policy: same-origin`. Request bodies over 64 KB are refused. `/api/health` says nothing about
  data.

## The watch API

All JSON. The token comes from linking and goes in `Authorization: Bearer …`.

| Call | Does |
|---|---|
| `GET /api/health` | `{ ok, app: "gkg", version }` |
| `POST /api/watch/pair` | `{ code, secret, expiresIn }`: show the code, keep the secret |
| `POST /api/watch/status` `{ secret }` | `{ status: "waiting" }`, or `{ status: "linked", token }` once; 404 when the code is gone (get a new one) |
| `GET /api/watch/lists?rev=` | `{ rev, syncedAt, lists, keep }`, or `{ rev, same: true }` when nothing changed since `rev` |
| `POST /api/watch/changes` `{ changes }` | applies those that touch the lists it was given, syncs with Keep once, answers like `lists` plus `{ applied, skipped }`; 503 when Keep could not be reached (send them again later) |

A list: `{ id, title, kind: "list", pinned, open, items: [{ id, text, done, sub? }] }`;
a plain note (when turned on): `{ id, title, kind: "note", pinned, text }`.
A change: `{ op: "check", list, item, done }` (the server also takes `{ op: "add", list, text }`, which the watch does not send yet).
Setting `done` is idempotent, so a change sent twice does no harm. Any call can answer
401: the watch was unlinked, back to a code. When the watch asks for its lists and the
server's last sync with Keep is older than 30 seconds, the server syncs first.

## Working on it

```bash
pip install -r requirements-dev.txt
python -m pytest -q
GKG_DATA_DIR=./data uvicorn app.main:create_app --factory --port 8791
```

The watch app is in `garmin/` (Connect IQ, Monkey C; 74 round watches with buttons); build it
with the Connect IQ SDK and your own developer key, see [garmin/README.md](garmin/README.md).

## License

MIT, see [LICENSE](LICENSE).
