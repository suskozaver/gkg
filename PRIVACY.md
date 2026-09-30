# GKG — Privacy Policy

*Effective 29 September 2026, updated 30 September 2026.*

GKG is a Connect IQ app for Garmin watches that shows lists from Google Keep and lets
you tick items off. It is not affiliated with, endorsed by or sponsored by Google or
Garmin.

## What the watch app sends, and where

The app talks to **one server only: the GKG server whose address you enter** in the
app's settings (Garmin Connect › GKG › Settings). It sends nothing anywhere else, has
no analytics, no advertising and no tracking, and the developer of the app receives
nothing from it.

Through your phone's connection, the app sends that server:

- a request for a six-digit linking code, and then the code's secret, to link the watch;
- a token it was given when linked, with every request, so the server knows the watch;
- which items you ticked or unticked, and in which list.

It receives from the server the lists chosen there: their titles and items and whether
each item is ticked, and the text of plain notes, if they are turned on there. The watch keeps the last lists it received, the token and any
ticks not yet sent, on the watch only. **Unlink watch** in the app's menu, or removing
the app, deletes them.

## The server

The GKG server is software you run yourself (or someone you trust runs for you); its
code is published in this repository. Whoever runs a server is responsible for the data
on it. As published, the server:

- keeps one account (a username and a scrypt hash of the password);
- connects to Google Keep with a token for your Google account, which it stores only
  encrypted, and caches your notes encrypted between restarts;
- keeps, for each linked watch, only a hash of its token and when it was linked and last
  seen;
- sends nothing to anyone but Google Keep, and nothing about your data to the
  developer.

Disconnecting Keep on the server deletes the token and the cached notes; unlinking a
watch on the server revokes its token at once.

## Changes

A change to this policy is published here, with its date.

## Contact

Questions: open an issue in this repository.
