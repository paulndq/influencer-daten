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
