"""Holt Google-Trends-Verläufe (Suchinteresse) für typische Bitcoin-Suchbegriffe nach data/trends.json.

Aufruf:  python fetch_trends.py                    (alle Zeiträume)
         python fetch_trends.py --frames d90       (nur die letzten 90 Tage, täglich)
Zeiträume: d90 = 90 Tage täglich, w5 = 5 Jahre wöchentlich, all = seit 2004 monatlich.
Begriffe stehen in trends_terms.json (Text oder {"q": "...", "geo": "DE"}).

Wichtig: Google bietet dafür keine offizielle Schnittstelle, es wird pytrends benutzt. Google blockiert
Rechenzentren (also auch GitHub Actions) häufig mit Fehler 429. Dann das Skript auf dem eigenen Rechner
ausführen (pip install pytrends) und data/trends.json ins Repo hochladen.
Jeder Wert ist relativ zum Höchstwert des jeweiligen Wortes im Zeitraum (100), nicht absolute Suchanzahl.
"""
import argparse, json, random, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
OUT = DATA / "trends.json"
TERMS_FILE = ROOT / "trends_terms.json"
FRAMES = {"d90": "today 3-m", "w5": "today 5-y", "all": "all"}


def load_terms():
    raw = json.loads(TERMS_FILE.read_text(encoding="utf-8"))
    return [{"q": t, "geo": ""} if isinstance(t, str) else {"q": t["q"], "geo": t.get("geo", "")} for t in raw]


def fetch_one(pt, q, geo, tf):
    pt.build_payload([q], timeframe=tf, geo=geo)
    df = pt.interest_over_time()
    if df.empty or q not in df:
        return None
    if "isPartial" in df:
        df = df[~df["isPartial"].astype(bool)]  # unvollständigen letzten Zeitraum weglassen
    return {"dates": [d.strftime("%Y-%m-%d") for d in df.index], "values": [int(v) for v in df[q]]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", default="d90,w5,all")
    args = ap.parse_args()
    frames = [f.strip() for f in args.frames.split(",") if f.strip() in FRAMES]
    if not frames:
        sys.exit("Fehler: --frames braucht d90, w5 und/oder all.")
    try:
        from pytrends.request import TrendReq
    except ImportError:
        sys.exit("Fehler: pytrends fehlt (pip install pytrends).")
    DATA.mkdir(exist_ok=True)
    try:
        pt = TrendReq(hl="de-DE", tz=0, timeout=(10, 30))  # kontaktiert Google bereits beim Anlegen
    except Exception as e:
        sys.exit(f"Fehler: Google nicht erreichbar oder blockiert ({e}). Später oder lokal erneut versuchen.")
    terms = load_terms()
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    series = data.setdefault("series", {})
    got, fails, stop = 0, 0, False
    for fr in frames:
        for t in terms:
            ok = False
            for attempt in range(3):
                try:
                    res = fetch_one(pt, t["q"], t["geo"], FRAMES[fr])
                    if res:
                        series.setdefault(fr, {})[t["q"]] = res
                        got += 1
                        ok = True
                    break
                except Exception as e:  # pytrends wirft verschiedene Fehlerarten
                    print(f"Warnung: {t['q']} ({fr}), Versuch {attempt + 1}: {e}", file=sys.stderr)
                    time.sleep(45 * (attempt + 1))
            fails = 0 if ok else fails + 1
            if fails >= 3:
                print("Abbruch: Google blockiert offenbar die Anfragen (3 Begriffe in Folge ohne Ergebnis).", file=sys.stderr)
                stop = True
                break
            time.sleep(random.uniform(6, 12))
        if stop:
            break
    if not got:
        sys.exit("Keine Google-Daten erhalten. Vermutlich blockiert, später oder lokal erneut versuchen.")
    names = [t["q"] for t in terms]
    for fr in list(series):
        series[fr] = {q: v for q, v in series[fr].items() if q in names}
    data["terms"] = names
    data["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"{got} Verläufe gespeichert ({', '.join(f'{fr}: {len(series.get(fr, {}))}' for fr in frames)}).")


if __name__ == "__main__":
    main()
