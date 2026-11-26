# BTC & Krypto-Influencer

## Einrichten (einmalig)
1. API-Key: console.cloud.google.com → neues Projekt → "YouTube Data API v3" aktivieren → Anmeldedaten → API-Schlüssel.
2. Neues GitHub-Repo anlegen und diese Dateien hochladen.
3. Repo → Settings → Secrets and variables → Actions → New secret: Name `YT_API_KEY`, Wert = dein Key.
4. Repo → Settings → Pages → Branch `main`, Ordner `/ (root)` → Seite ist online.
5. Actions-Tab → "Daten sammeln" → "Run workflow" für den ersten Lauf. Danach läuft es täglich selbst.

## Lokal testen
    pip install requests
    export YT_API_KEY=dein_key        # Windows: set YT_API_KEY=dein_key
    python collect.py
    python -m http.server 8000        # dann http://localhost:8000

## Kanäle erweitern
`channels.json` bearbeiten (Kanal-ID beginnt mit "UC"). Die ID findest du auf youtube.com/account_advanced
oder über die Kanalseite → "Mehr" → "Kanal teilen" → "Kanal-ID kopieren".

## Kanäle aus aller Welt finden
Actions → "Kanäle finden" → Run workflow. Im Feld steht, wie viele Kanäle pro Region direkt in `channels.json`
eingetragen werden (0 = nur Vorschläge in `data/candidates.txt`). Ein Lauf kostet ca. 5.000 von 10.000
API-Einheiten pro Tag, also nicht mehrmals am Tag starten. Danach `channels.json` durchsehen und
Kanäle löschen, die nicht passen (Signal-Verkäufer, Giveaway-Kanäle, falsche Region).

## Neue Datenfelder
`data/videos.csv`: Uploads der letzten 7 Tage sowie Views, Likes, Kommentare der 10 neuesten Videos pro Kanal.
Kosten ca. 2 API-Einheiten pro Kanal und Tag. Gesammelt wird ab dem ersten Lauf, rückwirkend gibt es das nicht.
