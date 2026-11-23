"""Sammelt täglich YouTube-Kanalstatistiken und den BTC-Preis.

Benötigt: Python 3.9+, `pip install requests`, Umgebungsvariable YT_API_KEY.
Kosten pro Lauf: ~1 API-Einheit pro 50 Kanäle (channels.list).
"""
import csv, json, os, sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
DATA = ROOT / "data"
YT_CSV = DATA / "youtube.csv"
BTC_CSV = DATA / "btc.csv"
OUT_JSON = DATA / "data.json"
FIELDS = ["date", "channel_id", "views", "subscribers", "videos"]


def load_channels():
    return json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))


def fetch_youtube(channels, key):
    rows, today = [], date.today().isoformat()
    ids = [c["id"] for c in channels]
    for i in range(0, len(ids), 50):  # max. 50 IDs pro Abfrage
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "statistics", "id": ",".join(ids[i:i + 50]), "key": key},
            timeout=30,
        )
        r.raise_for_status()
        for item in r.json().get("items", []):
            s = item["statistics"]
            rows.append({
                "date": today,
                "channel_id": item["id"],
                "views": int(s.get("viewCount", 0)),
                "subscribers": int(s.get("subscriberCount", 0)),
                "videos": int(s.get("videoCount", 0)),
            })
    found = {r["channel_id"] for r in rows}
    for c in channels:
        if c["id"] not in found:
            print(f"Warnung: Kanal nicht gefunden: {c['name']} ({c['id']})", file=sys.stderr)
    return rows


def append_youtube(rows):
    old = []
    if YT_CSV.exists():
        with YT_CSV.open(encoding="utf-8") as f:
            old = list(csv.DictReader(f))
    today = rows[0]["date"] if rows else None
    old = [r for r in old if r["date"] != today]  # Neustart am selben Tag überschreibt
    with YT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(old + rows)


def fetch_btc():
    """Tageskerzen von Kraken (kein API-Key nötig, ca. 720 Tage)."""
    r = requests.get(
        "https://api.kraken.com/0/public/OHLC",
        params={"pair": "XBTUSD", "interval": 1440},
        timeout=30,
    )
    r.raise_for_status()
    result = r.json()["result"]
    candles = next(v for k, v in result.items() if k != "last")
    out = {}
    for c in candles:
        d = datetime.fromtimestamp(c[0], tz=timezone.utc).date().isoformat()
        out[d] = float(c[4])  # Schlusskurs
    with BTC_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "close"])
        for d, p in sorted(out.items()):
            w.writerow([d, p])
    return out


def build_json(btc):
    """Pro Tag: Summe der Tageszuwächse der Views über alle Kanäle."""
    per_channel = defaultdict(dict)
    with YT_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            per_channel[r["channel_id"]][r["date"]] = (int(r["views"]), int(r["subscribers"]))
    delta, subs = defaultdict(int), defaultdict(int)
    for series in per_channel.values():
        days = sorted(series)
        for prev, cur in zip(days, days[1:]):
            gap = (date.fromisoformat(cur) - date.fromisoformat(prev)).days
            if gap == 1:  # nur lückenlose Tage, sonst verfälscht
                delta[cur] += series[cur][0] - series[prev][0]
        for d in days:
            subs[d] += series[d][1]
    days = sorted(set(delta) | set(subs))
    rows = [{
        "date": d,
        "btc": btc.get(d),
        "views_delta": delta.get(d),
        "subscribers": subs.get(d),
    } for d in days]
    OUT_JSON.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "btc_history": [{"date": d, "close": p} for d, p in sorted(btc.items())],
        "rows": rows,
    }), encoding="utf-8")
    print(f"{len(rows)} Tage mit Influencer-Daten, {len(btc)} Tage BTC.")


def main():
    key = os.environ.get("YT_API_KEY")
    if not key:
        sys.exit("Fehler: YT_API_KEY ist nicht gesetzt.")
    DATA.mkdir(exist_ok=True)
    rows = fetch_youtube(load_channels(), key)
    if rows:
        append_youtube(rows)
    btc = fetch_btc()
    build_json(btc)


if __name__ == "__main__":
    main()
