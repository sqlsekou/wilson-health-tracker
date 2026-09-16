"""
Merge data/inspections.csv with data/geocode_cache.csv and write the files the
dashboard and BI tools read:

  data/inspections.json   {"meta": {...}, "rows": [[name, score, result_text, street, city,
                           zip, facility_type, inspection_type, date, lat, lon], ...]}
  data/inspections.csv    same rows with source_url, geo_source, geo_precision filled in

Coordinates come only from the cache. An address with no match stays null.

Usage:
    python scripts/build.py
"""
import csv
import json
import os
from datetime import datetime, timezone

from common import GEOCODE_CACHE, INSPECTIONS_JSON, geo_key, normalize_city, normalize_facility, read_inspections, sort_rows, write_inspections

SOURCE_NAME = "Wilson County Source"
SOURCE_URL = "https://wilsoncountysource.com"


def load_cache():
    if not GEOCODE_CACHE.exists():
        return {}
    with GEOCODE_CACHE.open(newline="", encoding="utf-8") as f:
        return {r["key"]: r for r in csv.DictReader(f)}


def to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def to_float(v):
    try:
        return round(float(v), 6)
    except (TypeError, ValueError):
        return None


def main():
    rows = read_inspections()
    cache = load_cache()

    clean = []
    for r in rows:
        r = dict(r)
        r["city"] = normalize_city(r["city"])
        r["facility_type"] = normalize_facility(r["facility_type"])
        r["zip"] = str(r["zip"]).strip()[:5]
        score = to_int(r["score"])
        r["score"] = score
        if score is None and not r["result_text"]:
            r["result_text"] = ""
        c = cache.get(geo_key(r["street"], r["city"], r["zip"]))
        if c and c.get("lat"):
            r["lat"], r["lon"] = to_float(c["lat"]), to_float(c["lon"])
            r["geo_source"], r["geo_precision"] = c["source"], c["precision"]
        else:
            r["lat"] = r["lon"] = None
            r["geo_source"] = c["source"] if c else ""
            r["geo_precision"] = ""
        clean.append(r)

    clean = sort_rows(clean)
    write_inspections(clean)

    dates = [r["date"] for r in clean if r["date"]]
    scored = [r for r in clean if r["score"] is not None]
    meta = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "underlying": "Tennessee Department of Health inspections",
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "count": len(clean),
        "scored": len(scored),
        "mapped": sum(1 for r in clean if r["lat"] is not None),
        "fields": ["name", "score", "result_text", "street", "city", "zip",
                   "facility_type", "inspection_type", "date", "lat", "lon"],
    }
    out = {"meta": meta, "rows": [
        [r["name"], r["score"], r["result_text"], r["street"], r["city"], r["zip"],
         r["facility_type"], r["inspection_type"], r["date"], r["lat"], r["lon"]]
        for r in clean
    ]}
    INSPECTIONS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with INSPECTIONS_JSON.open("w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")

    print(f"Build: {meta['count']} inspections, {meta['scored']} scored, {meta['mapped']} mapped, "
          f"{meta['date_min']} to {meta['date_max']}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"latest_date={meta['date_max']}\n")
            f.write(f"total={meta['count']}\n")


if __name__ == "__main__":
    main()
