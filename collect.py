"""Sammelt täglich YouTube-Kanalstatistiken und den BTC-Preis.

Benötigt: Python 3.9+, `pip install requests`, Umgebungsvariable YT_API_KEY.
Kosten pro Lauf: ~1 API-Einheit pro 50 Kanäle (channels.list).
"""
import csv, json, os, sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
DATA = ROOT / "data"
YT_CSV = DATA / "youtube.csv"
VID_CSV = DATA / "videos.csv"
BTC_CSV = DATA / "btc.csv"
OUT_JSON = DATA / "data.json"
FIELDS = ["date", "channel_id", "views", "subscribers", "videos"]
VFIELDS = ["date", "channel_id", "uploads_7d", "views", "likes", "comments", "n"]
API = "https://www.googleapis.com/youtube/v3"


def load_channels():
    return json.loads((ROOT / "channels.json").read_text(encoding="utf-8"))


def resolve_channels(channels, key):
    """Wandelt @Handles in Kanal-IDs um (einmalig, Ergebnis wird in data/handles.json gemerkt)."""
    cache_file = DATA / "handles.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    out, seen = [], set()
    for c in channels:
        cid = c.get("id")
        if not cid:
            h = (c.get("handle") or "").strip()
            if not h:
                print(f"Warnung: Eintrag ohne id oder handle: {c}", file=sys.stderr)
                continue
            if not h.startswith("@"):
                h = "@" + h
            if h.lower() not in cache:
                r = requests.get(
                    "https://www.googleapis.com/youtube/v3/channels",
                    params={"part": "id", "forHandle": h, "key": key},
                    timeout=30,
                )
                r.raise_for_status()
                items = r.json().get("items", [])
                if not items:
                    print(f"Warnung: Handle nicht gefunden: {h}", file=sys.stderr)
                    continue
                cache[h.lower()] = items[0]["id"]
            cid = cache[h.lower()]
        if cid in seen:
            print(f"Hinweis: Kanal doppelt eingetragen: {c.get('name', cid)}", file=sys.stderr)
            continue
        seen.add(cid)
        out.append({**c, "id": cid})
    cache_file.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return out


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


def append_csv(path, fields, rows):
    old = []
    if path.exists():
        with path.open(encoding="utf-8") as f:
            old = list(csv.DictReader(f))
    if rows:
        old = [r for r in old if r["date"] != rows[0]["date"]]  # Neustart am selben Tag überschreibt
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(old + rows)


def fetch_videos(channels, key):
    """Pro Kanal: neueste Videos -> Uploads der letzten 7 Tage, Views/Likes/Kommentare der 10 neuesten.
    Kosten: ca. 2 API-Einheiten pro Kanal."""
    rows, today = [], date.today().isoformat()
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    s = requests.Session()
    for c in channels:
        cid = c["id"]
        try:
            r = s.get(f"{API}/playlistItems", timeout=30, params={
                "part": "contentDetails", "playlistId": "UU" + cid[2:], "maxResults": 15, "key": key})
            r.raise_for_status()
            items = r.json().get("items", [])
            if not items:
                continue
            ids = [i["contentDetails"]["videoId"] for i in items]
            uploads = 0
            for i in items:
                p = i["contentDetails"].get("videoPublishedAt")
                if p and datetime.fromisoformat(p.replace("Z", "+00:00")) >= cutoff:
                    uploads += 1
            r = s.get(f"{API}/videos", timeout=30, params={
                "part": "statistics", "id": ",".join(ids[:10]), "key": key})
            r.raise_for_status()
            stats = [v.get("statistics", {}) for v in r.json().get("items", [])]
            rows.append({
                "date": today, "channel_id": cid, "uploads_7d": uploads,
                "views": sum(int(x.get("viewCount", 0)) for x in stats),
                "likes": sum(int(x.get("likeCount", 0)) for x in stats),
                "comments": sum(int(x.get("commentCount", 0)) for x in stats),
                "n": len(stats),
            })
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                print("Warnung: API-Kontingent erschöpft, Videodaten abgebrochen.", file=sys.stderr)
                break
            print(f"Warnung: Videodaten fehlen für {c.get('name', cid)}: {e}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"Warnung: Videodaten fehlen für {c.get('name', cid)}: {e}", file=sys.stderr)
    return rows


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


def channel_info():
    """Kanal-ID -> Name und Region, aus channels.json (Handles über data/handles.json aufgelöst)."""
    cache_file = DATA / "handles.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    out = {}
    for c in load_channels():
        cid = c.get("id")
        if not cid:
            h = (c.get("handle") or "").strip()
            if h and not h.startswith("@"):
                h = "@" + h
            cid = cache.get(h.lower())
        if cid:
            out[cid] = {"name": c.get("name", cid), "region": c.get("region", "?")}
    return out


def build_json(btc):
    """Pro Tag: Zuwachs der Views pro Kanal/Region/gesamt, dazu Aktivität (Uploads, Likes, Kommentare)."""
    info = channel_info()
    per_channel = defaultdict(dict)
    with YT_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            per_channel[r["channel_id"]][r["date"]] = (int(r["views"]), int(r["subscribers"]))
    vids = defaultdict(dict)  # Datum -> Kanal -> Zeile
    if VID_CSV.exists():
        with VID_CSV.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                vids[r["date"]][r["channel_id"]] = r
    delta, subs = defaultdict(int), defaultdict(int)
    rdelta = defaultdict(lambda: defaultdict(int))
    chdelta = defaultdict(dict)
    for cid, series in per_channel.items():
        region = info.get(cid, {}).get("region", "?")
        days = sorted(series)
        for prev, cur in zip(days, days[1:]):
            gap = (date.fromisoformat(cur) - date.fromisoformat(prev)).days
            if gap == 1:  # nur lückenlose Tage, sonst verfälscht
                dv = series[cur][0] - series[prev][0]
                delta[cur] += dv
                rdelta[cur][region] += dv
                chdelta[cur][cid] = dv
        for d in days:
            subs[d] += series[d][1]
    ext = defaultdict(lambda: defaultdict(lambda: {"l": 0, "c": 0, "v": 0, "u": 0}))
    latest_v = {}
    for d in sorted(vids):
        for cid, r in vids[d].items():
            e = ext[d][info.get(cid, {}).get("region", "?")]
            e["l"] += int(r["likes"]); e["c"] += int(r["comments"])
            e["v"] += int(r["views"]); e["u"] += int(r["uploads_7d"])
            latest_v[cid] = r
    days = sorted(set(delta) | set(subs) | set(vids))
    rows = [{
        "date": d,
        "btc": btc.get(d),
        "views_delta": delta.get(d),
        "regions": dict(rdelta.get(d, {})),
        "ch": chdelta.get(d, {}),
        "ext": {g: e for g, e in ext.get(d, {}).items()},
        "subscribers": subs.get(d),
    } for d in days]
    channels = []
    for cid, i in info.items():
        if cid not in per_channel:
            continue
        views, sub = per_channel[cid][max(per_channel[cid])]
        m = {"id": cid, "name": i["name"], "region": i["region"], "subs": sub, "views": views}
        r = latest_v.get(cid)
        if r:
            v = int(r["views"])
            m["eng"] = round((int(r["likes"]) + int(r["comments"])) / v, 4) if v else None
            m["u7"] = int(r["uploads_7d"])
        channels.append(m)
    OUT_JSON.write_text(json.dumps({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "btc_history": [{"date": d, "close": p} for d, p in sorted(btc.items())],
        "channels": channels,
        "rows": rows,
    }), encoding="utf-8")
    print(f"{len(rows)} Tage mit Influencer-Daten, {len(btc)} Tage BTC, {len(channels)} Kanäle.")


def main():
    key = os.environ.get("YT_API_KEY")
    if not key:
        sys.exit("Fehler: YT_API_KEY ist nicht gesetzt.")
    DATA.mkdir(exist_ok=True)
    channels = resolve_channels(load_channels(), key)
    rows = fetch_youtube(channels, key)
    if rows:
        append_csv(YT_CSV, FIELDS, rows)
    vrows = fetch_videos(channels, key)
    if vrows:
        append_csv(VID_CSV, VFIELDS, vrows)
    btc = fetch_btc()
    build_json(btc)


if __name__ == "__main__":
    main()
