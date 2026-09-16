"""
Geocode addresses in data/inspections.csv that are not yet in data/geocode_cache.csv.

1. US Census Bureau batch geocoder (free, no API key, public domain results)
2. OpenStreetMap Nominatim for anything Census cannot match (1 request per second)
3. City and zip centroid as a last resort, labeled geo_precision = "city centroid"

The cache is the only thing this script writes. build.py joins it back onto the
rows. Never regenerate the cache from scratch; it is the record of every lookup.

Usage:
    python scripts/geocode.py
    python scripts/geocode.py --retry-unmatched   # try again for addresses that never matched
"""
import argparse
import csv
import io
import sys
import time

import requests

from common import GEOCODE_CACHE, USER_AGENT, clean_street, geo_key, read_inspections

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
CACHE_FIELDS = ["key", "street", "city", "zip", "lat", "lon", "source", "precision"]
CENSUS_BATCH_LIMIT = 5000


def load_cache():
    if not GEOCODE_CACHE.exists():
        return {}
    with GEOCODE_CACHE.open(newline="", encoding="utf-8") as f:
        return {r["key"]: r for r in csv.DictReader(f)}


def save_cache(cache):
    GEOCODE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with GEOCODE_CACHE.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CACHE_FIELDS, extrasaction="ignore")
        w.writeheader()
        for k in sorted(cache):
            w.writerow({fld: cache[k].get(fld, "") for fld in CACHE_FIELDS})


def census_batch(pending):
    """pending: {key: (street, city, zip)}. Returns {key: (lat, lon, match_kind)}."""
    out = {}
    items = list(pending.items())
    for start in range(0, len(items), CENSUS_BATCH_LIMIT):
        chunk = items[start:start + CENSUS_BATCH_LIMIT]
        buf = io.StringIO()
        ids = {}
        for i, (k, (street, city, zc)) in enumerate(chunk):
            ids[str(i)] = k
            csv.writer(buf).writerow([i, street, city, "TN", zc])
        resp = requests.post(
            CENSUS_URL,
            files={"addressFile": ("addresses.csv", buf.getvalue(), "text/csv")},
            data={"benchmark": "Public_AR_Current"},
            headers={"User-Agent": USER_AGENT},
            timeout=300,
        )
        resp.raise_for_status()
        for rec in csv.reader(io.StringIO(resp.text)):
            # id, input, Match/No_Match/Tie, Exact/Non_Exact, matched address, "lon,lat", tigerline id, side
            if len(rec) >= 6 and rec[2] == "Match" and rec[5]:
                lon, lat = rec[5].split(",")
                out[ids[rec[0]]] = (float(lat), float(lon), rec[3].lower())
    return out


def nominatim(params):
    for attempt in range(3):
        time.sleep(1.5)  # Nominatim usage policy: max 1 request per second
        r = requests.get(
            NOMINATIM_URL,
            params={**params, "format": "json", "limit": 1, "countrycodes": "us"},
            headers={"User-Agent": USER_AGENT},
            timeout=30,
        )
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        hits = r.json()
        return (float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None
    r.raise_for_status()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retry-unmatched", action="store_true")
    ap.add_argument("--no-nominatim", action="store_true", help="Census only (faster, for testing)")
    args = ap.parse_args()

    rows = read_inspections()
    cache = load_cache()

    pending = {}
    for r in rows:
        if not r["street"] or not r["city"]:
            continue
        k = geo_key(r["street"], r["city"], r["zip"])
        if k in cache and not (args.retry_unmatched and cache[k]["source"] == "unmatched"):
            continue
        pending[k] = (clean_street(r["street"]), r["city"], r["zip"])

    if not pending:
        print("Geocode: nothing new to look up")
        return

    print(f"Geocode: {len(pending)} new addresses")
    print("  Census batch...")
    try:
        matched = census_batch(pending)
    except requests.RequestException as e:
        print(f"  Census geocoder unavailable ({e}); trying Nominatim only", file=sys.stderr)
        matched = {}
    for k, (lat, lon, kind) in matched.items():
        st, ci, zc = pending[k]
        cache[k] = dict(key=k, street=st, city=ci, zip=zc, lat=lat, lon=lon,
                        source="census", precision=f"address ({kind})")
    print(f"  Census matched {len(matched)} of {len(pending)}")
    save_cache(cache)

    leftover = [k for k in pending if k not in cache or cache[k]["source"] == "unmatched"]
    if args.no_nominatim or not leftover:
        return

    print(f"  Nominatim for {len(leftover)} leftover addresses (about {len(leftover) * 2} seconds)...")
    centroids = {}  # (city, zip) -> hit, so each centroid is looked up once per run
    for k in leftover:
        st, ci, zc = pending[k]
        try:
            hit = nominatim({"street": st, "city": ci, "state": "TN", "postalcode": zc})
            if hit:
                cache[k] = dict(key=k, street=st, city=ci, zip=zc, lat=hit[0], lon=hit[1],
                                source="nominatim", precision="address")
            else:
                if (ci, zc) not in centroids:
                    centroids[(ci, zc)] = nominatim({"city": ci, "state": "TN", "postalcode": zc}) or nominatim({"city": ci, "state": "TN"})
                hit = centroids[(ci, zc)]
                if hit:
                    cache[k] = dict(key=k, street=st, city=ci, zip=zc, lat=hit[0], lon=hit[1],
                                    source="nominatim", precision="city centroid")
                else:
                    cache[k] = dict(key=k, street=st, city=ci, zip=zc, lat="", lon="",
                                    source="unmatched", precision="")
                    print(f"  Unmatched: {st}, {ci} {zc}")
        except requests.RequestException as e:
            print(f"  Nominatim error for {st}, {ci}: {e}", file=sys.stderr)
        save_cache(cache)  # after every lookup, so an interrupted run keeps what it found

    placed = sum(1 for r in rows if cache.get(geo_key(r["street"], r["city"], r["zip"]), {}).get("lat"))
    print(f"Done: {placed} of {len(rows)} rows have coordinates in the cache")


if __name__ == "__main__":
    main()
