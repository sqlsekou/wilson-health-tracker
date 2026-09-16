"""
Shared paths, field names, and cleaning helpers for the Wilson County
health inspection pipeline. Imported by scrape.py, geocode.py, and build.py.
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "cache" / "posts"

INSPECTIONS_CSV = DATA_DIR / "inspections.csv"
INSPECTIONS_JSON = DATA_DIR / "inspections.json"
GEOCODE_CACHE = DATA_DIR / "geocode_cache.csv"
POSTS_SEEN = DATA_DIR / "posts_seen.json"

USER_AGENT = "RoyalBlueAnalytics-WilsonHealthTracker/1.0 (+https://royalblueanalytics.com)"

# Column order for data/inspections.csv. The first eleven match the JSON record order
# the dashboard expects; the last three are provenance columns for humans and BI tools.
CSV_FIELDS = [
    "name", "score", "result_text", "street", "city", "zip",
    "facility_type", "inspection_type", "date", "lat", "lon",
    "source_url", "geo_source", "geo_precision",
]

# Spellings seen in the source tables, mapped to one display name each.
CITY_ALIASES = {
    "mt juliet": "Mt. Juliet",
    "mt. juliet": "Mt. Juliet",
    "mt.juliet": "Mt. Juliet",
    "mount juliet": "Mt. Juliet",
    "lebanon": "Lebanon",
    "old hickory": "Old Hickory",
    "watertown": "Watertown",
    "hermitage": "Hermitage",
    "gladeville": "Gladeville",
    "norene": "Norene",
    "nashville": "Nashville",
    "green hill": "Green Hill",
    "la vergne": "La Vergne",
    "lavergne": "La Vergne",
    "smyrna": "Smyrna",
    "murfreesboro": "Murfreesboro",
    "gallatin": "Gallatin",
    "hendersonville": "Hendersonville",
    "brentwood": "Brentwood",
    "franklin": "Franklin",
    "antioch": "Antioch",
    "madison": "Madison",
    "goodlettsville": "Goodlettsville",
    "carthage": "Carthage",
    "alexandria": "Alexandria",
    "statesville": "Statesville",
    "castalian springs": "Castalian Springs",
    "rural hill": "Rural Hill",
    "brush creek": "Brush Creek",
    "lascassas": "Lascassas",
    "lafayette": "Lafayette",
    "hartsville": "Hartsville",
    "cookeville": "Cookeville",
    "portland": "Portland",
    "springfield": "Springfield",
    "johnson city": "Johnson City",
    "chattanooga": "Chattanooga",
    "hixson": "Hixson",
    "spencer": "Spencer",
    "cleveland": "Cleveland",
    "knoxville": "Knoxville",
    "seymour": "Seymour",
    "crossville": "Crossville",
    "niota": "Niota",
}

# Facility type labels as published (after stripping a trailing "Inspection" or
# "Establishment"), mapped to the short labels the dashboard uses.
FACILITY_ALIASES = {
    "food service": "Food Service",
    "mobile food units": "Food Service",
    "temporary food service": "Food Service",
    "public swimming pools": "Swimming Pools",
    "swimming pools": "Swimming Pools",
    "swimming pool": "Swimming Pools",
    "child care": "Child Care Facilities",
    "child care facilities": "Child Care Facilities",
    "child care facility": "Child Care Facilities",
    "tattoo studios": "Tattoo Studios",
    "tattoo studio": "Tattoo Studios",
    "tattoo": "Tattoo Studios",
    "body piercing studios": "Body Piercing Studios",
    "body piercing studio": "Body Piercing Studios",
    "school buildings": "School Buildings",
    "school building": "School Buildings",
    "hotels motels": "Hotels and Motels",
    "hotels/motels": "Hotels and Motels",
    "hotels and motels": "Hotels and Motels",
    "hotel/motel": "Hotels and Motels",
    "bed and breakfast": "Bed and Breakfast",
    "bed & breakfast": "Bed and Breakfast",
    "organized camps": "Campgrounds",
    "organized camp": "Campgrounds",
    "organized campgrounds": "Campgrounds",
    "campgrounds": "Campgrounds",
    "campground": "Campgrounds",
}

INSPECTION_TYPES = ["Routine", "Follow-Up", "Complaint", "Complete", "Preliminary", "Pre-Opening", "Consultation"]


def normalize_city(city: str) -> str:
    c = re.sub(r"\s+", " ", city or "").strip(" ,.")
    return CITY_ALIASES.get(c.lower(), c.title())


def normalize_facility(label: str) -> str:
    f = re.sub(r"\s+", " ", label or "").strip(" -|")
    f = re.sub(r"\s+(establishment\s+)?inspections?$", "", f, flags=re.I)
    f = re.sub(r"\s+establishments?$", "", f, flags=re.I)
    return FACILITY_ALIASES.get(f.lower(), f)


def clean_street(street: str) -> str:
    """Clean a street string for geocoding and for grouping pins on the map."""
    s = street or ""
    s = re.sub(r"^(\d+)([A-Za-z])", r"\1 \2", s)                                # 100Reunion -> 100 Reunion
    s = re.sub(r"\b(?:ste|suite|unit|bldg|apt)\.?\s*#?\s*[\w-]+$", "", s, flags=re.I)  # drop suites
    s = re.sub(r"(\b(?:Rd|Dr|St|Blvd|Pkwy|Ln|Way|Wy|Cir|Ct|Ave|Hwy|Pike)\.?)\s+#?\d+[A-Za-z]?$", r"\1", s, flags=re.I)  # "Rd 102"
    s = s.replace("Mt.Juliet", "Mt. Juliet")
    s = re.sub(r"\.(?=\s|$)", "", s)                                                # "Ln." -> "Ln", "N." -> "N"
    return re.sub(r"\s+", " ", s).strip(" ,")


def geo_key(street: str, city: str, zip_code: str) -> str:
    """Address key shared by the geocode cache and the dashboard's pin grouping."""
    return f"{clean_street(street)}|{city}|{zip_code}".lower()


def dedupe_key(rec: dict) -> str:
    return "|".join([
        (rec.get("name") or "").strip().lower(),
        clean_street(rec.get("street") or "").lower(),
        rec.get("date") or "",
        (rec.get("inspection_type") or "").lower(),
    ])


def read_inspections() -> list[dict]:
    if not INSPECTIONS_CSV.exists():
        return []
    with INSPECTIONS_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # Accept the original hand-built CSV headers (Name, Score, Street, ...) as well.
    out = []
    for r in rows:
        if "name" in r:
            out.append({k: r.get(k, "") for k in CSV_FIELDS})
        else:
            out.append({
                "name": r.get("Name", ""), "score": r.get("Score", ""), "result_text": r.get("Result_Text", ""),
                "street": r.get("Street", ""), "city": r.get("City", ""), "zip": r.get("Zip", ""),
                "facility_type": r.get("Facility_Type", ""), "inspection_type": r.get("Inspection_Type", ""),
                "date": r.get("Inspection_Date", ""), "lat": "", "lon": "",
                "source_url": r.get("Source_URL", ""), "geo_source": "", "geo_precision": "",
            })
    return out


def write_inspections(rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with INSPECTIONS_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in CSV_FIELDS})


def sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (r.get("date") or "", (r.get("name") or "").lower(), r.get("inspection_type") or ""))
