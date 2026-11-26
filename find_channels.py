"""Findet Krypto-Kanäle aus aller Welt und schlägt sie vor.

Aufruf:  python find_channels.py            -> nur Vorschläge (data/candidates.json, data/candidates.txt)
         python find_channels.py --add 6    -> trägt zusätzlich die 6 größten pro Region in channels.json ein
Kosten:  ca. 5.000 API-Einheiten pro Lauf (Tageskontingent: 10.000). Nicht mehrmals am Tag starten.
"""
import argparse, json, os, sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).parent
DATA = ROOT / "data"
CHANNELS = ROOT / "channels.json"
API = "https://www.googleapis.com/youtube/v3"

# (Region, Land, Sprache, Suchbegriffe)
MARKETS = [
    ("EN", "US", "en", ["bitcoin price analysis", "crypto news today"]),
    ("EN", "GB", "en", ["bitcoin trading", "crypto market update"]),
    ("DACH", "DE", "de", ["bitcoin kurs", "krypto news"]),
    ("Spanisch", "ES", "es", ["bitcoin análisis", "criptomonedas noticias"]),
    ("Spanisch", "MX", "es", ["bitcoin precio hoy", "criptomonedas"]),
    ("Türkei", "TR", "tr", ["bitcoin analiz", "kripto para"]),
    ("Portugiesisch", "BR", "pt", ["bitcoin análise", "criptomoedas"]),
    ("Russisch", "RU", "ru", ["биткоин прогноз", "криптовалюта новости"]),
    ("Frankreich", "FR", "fr", ["bitcoin analyse", "cryptomonnaie actualité"]),
    ("Italien", "IT", "it", ["bitcoin analisi", "criptovalute notizie"]),
    ("Polen", "PL", "pl", ["bitcoin analiza", "kryptowaluty"]),
    ("Asien", "IN", "hi", ["bitcoin hindi", "crypto news hindi"]),
    ("Asien", "IN", "en", ["crypto india"]),
    ("Asien", "KR", "ko", ["비트코인", "코인 시황"]),
    ("Asien", "JP", "ja", ["ビットコイン", "仮想通貨"]),
    ("Asien", "TW", "zh", ["比特幣", "加密貨幣"]),
    ("Asien", "ID", "id", ["bitcoin analisa", "kripto"]),
    ("Asien", "VN", "vi", ["bitcoin phân tích", "tiền điện tử"]),
    ("Asien", "TH", "th", ["บิทคอยน์", "คริปโต"]),
    ("Asien", "SA", "ar", ["بيتكوين", "العملات الرقمية"]),
    ("Asien", "EG", "ar", ["بيتكوين تحليل", "كريبتو"]),
    ("Afrika", "NG", "en", ["bitcoin nigeria", "crypto nigeria"]),
]
# Ein Kanal muss eines dieser Wörter in Name oder Beschreibung haben, sonst ist er vermutlich kein Krypto-Kanal.
KEYWORDS = ["bitcoin", "btc", "crypto", "krypto", "cripto", "kripto", "blockchain", "ethereum", "altcoin",
            "coin", "биткоин", "крипто", "비트코인", "코인", "암호화폐", "ビットコイン", "仮想通貨", "暗号資産",
            "比特", "加密", "บิทคอยน์", "คริปโต", "بيتكوين", "كريبتو", "العملات الرقمية", "tiền điện tử", "tiền ảo"]


class QuotaError(Exception):
    pass


def api(path, **params):
    params["key"] = KEY
    r = requests.get(f"{API}/{path}", params=params, timeout=30)
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        if r.status_code == 403:
            raise QuotaError() from e
        raise
    return r.json()


def existing_ids():
    cache_file = DATA / "handles.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    ids = set()
    for c in json.loads(CHANNELS.read_text(encoding="utf-8")):
        if c.get("id"):
            ids.add(c["id"])
        else:
            h = (c.get("handle") or "").strip()
            if h and not h.startswith("@"):
                h = "@" + h
            if cache.get(h.lower()):
                ids.add(cache[h.lower()])
    return ids


def entry(c):
    if c["handle"].startswith("@"):
        return {"handle": c["handle"], "name": c["name"], "region": c["region"]}
    return {"id": c["id"], "name": c["name"], "region": c["region"]}


def main():
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", type=int, default=0, help="so viele Kanäle pro Region direkt eintragen")
    ap.add_argument("--min-subs", type=int, default=50000)
    ap.add_argument("--top", type=int, default=25, help="Vorschläge pro Region")
    args = ap.parse_args()
    KEY = os.environ.get("YT_API_KEY")
    if not KEY:
        sys.exit("Fehler: YT_API_KEY ist nicht gesetzt.")
    DATA.mkdir(exist_ok=True)
    have = existing_ids()

    found = {}
    try:
        for region, code, lang, queries in MARKETS:
            for q in queries:
                items = api("search", part="snippet", type="channel", q=q, regionCode=code,
                            relevanceLanguage=lang, maxResults=50).get("items", [])
                for it in items:
                    found.setdefault(it["id"]["channelId"], region)
    except QuotaError:
        print("Warnung: Kontingent erschöpft, arbeite mit den bisherigen Treffern weiter.", file=sys.stderr)
    found = {c: r for c, r in found.items() if c not in have}
    print(f"{len(found)} neue Kanäle gefunden, prüfe Größe und Inhalt ...")

    cands, ids = [], list(found)
    try:
        for i in range(0, len(ids), 50):
            for it in api("channels", part="snippet,statistics", id=",".join(ids[i:i + 50])).get("items", []):
                st, sn = it["statistics"], it["snippet"]
                if st.get("hiddenSubscriberCount"):
                    continue
                subs, vids = int(st.get("subscriberCount", 0)), int(st.get("videoCount", 0))
                text = (sn.get("title", "") + " " + sn.get("description", "")).lower()
                if subs < args.min_subs or vids < 30 or not any(k in text for k in KEYWORDS):
                    continue
                cands.append({"id": it["id"], "name": sn["title"].strip(), "handle": sn.get("customUrl", ""),
                              "region": found[it["id"]], "subs": subs, "videos": vids,
                              "country": sn.get("country", "")})
    except QuotaError:
        print("Warnung: Kontingent erschöpft beim Prüfen.", file=sys.stderr)

    limit = datetime.now(timezone.utc) - timedelta(days=60)
    active = []
    for c in cands:
        try:
            r = api("playlistItems", part="contentDetails", playlistId="UU" + c["id"][2:], maxResults=1)
        except QuotaError:
            break
        except requests.RequestException:
            continue
        items = r.get("items", [])
        p = items[0]["contentDetails"].get("videoPublishedAt") if items else None
        if p and datetime.fromisoformat(p.replace("Z", "+00:00")) >= limit:
            c["last_upload"] = p[:10]
            active.append(c)

    by = defaultdict(list)
    for c in sorted(active, key=lambda c: -c["subs"]):
        by[c["region"]].append(c)
    out = {g: v[:args.top] for g, v in by.items()}
    (DATA / "candidates.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = []
    for g in sorted(out):
        lines += [json.dumps(entry(c), ensure_ascii=False) + "," for c in out[g]] + [""]
    (DATA / "candidates.txt").write_text("\n".join(lines), encoding="utf-8")
    for g in sorted(out):
        print(f"{g}: {len(out[g])} Vorschläge, größter: {out[g][0]['name']} ({out[g][0]['subs']:,} Abos)")

    if args.add > 0:
        chs = json.loads(CHANNELS.read_text(encoding="utf-8"))
        n0 = len(chs)
        for g in sorted(out):
            chs += [entry(c) for c in out[g][:args.add]]
        CHANNELS.write_text("[\n  " + ",\n  ".join(json.dumps(c, ensure_ascii=False) for c in chs) + "\n]\n",
                            encoding="utf-8")
        print(f"{len(chs) - n0} Kanäle in channels.json eingetragen (jetzt {len(chs)}).")


if __name__ == "__main__":
    main()
