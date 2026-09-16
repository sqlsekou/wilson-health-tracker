"""
Find and parse "Health Scores: Wilson County" posts from Wilson County Source.

Discovery uses the WordPress REST API (verified working September 2026). Each post
is fetched once, cached under cache/posts/, parsed, and its rows are merged into
data/inspections.csv. Post URLs already processed are recorded in
data/posts_seen.json so weekly runs only touch new posts.

Three table layouts have appeared since January 2024 and all three are handled:
  * 2026:  Name | Score | Address | Type | Date            ("Food Service Routine")
  * 2025:  Facility Name | Score | Address | Inspection Type | Date   ("Food Service - Routine")
  * 2024:  one "Inspections List" column with five stacked rows per record

Usage:
    python scripts/scrape.py              # new posts only
    python scripts/scrape.py --all        # re-parse every post (uses the HTML cache)
    python scripts/scrape.py --primary-only
"""
import argparse
import html as htmllib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from common import (
    CACHE_DIR, CITY_ALIASES, INSPECTION_TYPES, POSTS_SEEN, USER_AGENT,
    dedupe_key, normalize_city, normalize_facility, read_inspections, sort_rows, write_inspections,
)

SITE = "https://wilsoncountysource.com"
API = f"{SITE}/wp-json/wp/v2/posts"
# The site tags every roundup. Tag ids looked up from /wp-json/wp/v2/tags?search=health
# (health scores = 2582, health inspections = 53). Search terms are a fallback in case tagging slips.
TAG_IDS = [2582, 53]
SEARCH_TERMS = ["health scores", "health inspections"]
REQUEST_GAP = 2.0  # seconds between requests to the site
MAX_RETRIES = 4

# Weekly roundup posts (the primary source).
PRIMARY_TITLE = re.compile(r"^\s*Health (Scores|Inspections):?\s*Wilson County", re.I)
# Lowest / perfect score roundups. Same table layout, same inspections; deduped against primary.
SECONDARY_TITLE = re.compile(r"^\s*(?:\d+\s+)?(Lowest|Perfect)\b.*Health Scores.*Wilson", re.I)

session = requests.Session()
session.headers["User-Agent"] = USER_AGENT
_last_request = 0.0


def polite_get(url, **kw):
    """One request at a time, spaced out, backing off when the site says slow down."""
    global _last_request
    for attempt in range(MAX_RETRIES + 1):
        wait = REQUEST_GAP - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        r = session.get(url, timeout=60, **kw)
        _last_request = time.monotonic()
        if r.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
            delay = int(r.headers.get("Retry-After") or 0) or 30 * (2 ** attempt)
            print(f"  {r.status_code} from site, waiting {delay}s", file=sys.stderr)
            time.sleep(delay)
            continue
        r.raise_for_status()
        return r


# ---------------------------------------------------------------- discovery

def discover_posts():
    """Return {url: {id, title, date, kind}} for every matching post."""
    found = {}
    queries = [{"tags": t} for t in TAG_IDS]
    for q in queries:
        page = 1
        while True:
            # orderby=date keeps pagination stable; relevance ordering drops posts between pages.
            r = polite_get(API, params={
                **q, "per_page": 100, "page": page, "orderby": "date", "order": "desc",
                "_fields": "id,date,link,title",
            })
            for p in r.json():
                title = htmllib.unescape(p["title"]["rendered"]).strip()
                kind = "primary" if PRIMARY_TITLE.search(title) else "secondary" if SECONDARY_TITLE.search(title) else None
                if kind:
                    found[p["link"]] = {"id": p["id"], "title": title, "date": p["date"][:10], "kind": kind}
            total_pages = int(r.headers.get("X-WP-TotalPages", "1"))
            if page >= total_pages:
                break
            page += 1
        if not found and q == queries[-1] and "search" not in q:
            queries += [{"search": t} for t in SEARCH_TERMS]  # tag lookup returned nothing; fall back to search
    return found


def fetch_post_html(url, post_id):
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    cache_file = CACHE_DIR / f"{slug}.html"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    r = polite_get(f"{API}/{post_id}", params={"_fields": "content"})
    content = r.json()["content"]["rendered"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(content, encoding="utf-8")
    return content


# ---------------------------------------------------------------- parsing

_city_alt = "|".join(sorted((re.escape(c) for c in CITY_ALIASES), key=len, reverse=True))
_state = r"(?:TN\.?|Tennessee)"
ADDR_KNOWN = re.compile(rf"^(?P<street>.*?)[\s,]+(?P<city>{_city_alt})\s*,?\s*{_state}\s*,?\s*(?P<zip>\d{{5}})(?:-\d{{4}})?\s*$", re.I)
ADDR_ANY = re.compile(rf"^(?P<street>.*)\s+(?P<city>[A-Za-z.]+)\s*,?\s*{_state}\s*,?\s*(?P<zip>\d{{5}})(?:-\d{{4}})?\s*$", re.I)
ADDR_LOOKS = re.compile(rf"\b{_state}\b.*\d{{5}}\s*$", re.I)

_itype_alt = "|".join(re.escape(t).replace(r"\-", r"[-\s]?") for t in INSPECTION_TYPES)
TYPE_RE = re.compile(rf"^(?P<fac>.*?)\s*(?:[-|–:]\s*)?(?P<itype>{_itype_alt})\s*$", re.I)

unknown_cities = {}


def parse_address(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    m = ADDR_KNOWN.match(text) or ADDR_ANY.match(text)
    if not m:
        return None
    city = normalize_city(m.group("city"))
    if m.group("city").lower().strip(" .,") not in CITY_ALIASES:
        unknown_cities.setdefault(city, text)
    return m.group("street").strip(" ,"), city, m.group("zip")


def parse_type(text):
    text = re.sub(r"\s+", " ", text or "").strip()
    m = TYPE_RE.match(text)
    if not m:
        return normalize_facility(text), ""
    itype = re.sub(r"[-\s]+", "-", m.group("itype").strip()).title()
    itype = {"Follow-Up": "Follow-Up", "Pre-Opening": "Pre-Opening"}.get(itype, itype)
    return normalize_facility(m.group("fac")), itype


def parse_score(text):
    text = (text or "").strip()
    if re.fullmatch(r"\d{1,3}", text):
        return int(text), ""
    if text.lower() in ("", "n/a", "na", "-", "none"):
        return None, ""
    return None, text


def parse_date(text):
    text = (text or "").strip()
    for fmt in ("%m/%d/%Y", "%B %d, %Y", "%b %d, %Y", "%b. %d, %Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def cells(tr):
    return [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]


def parse_wide_table(table, source_url, default_facility=""):
    """Five-column layout used from 2025 on."""
    rows = table.find_all("tr")
    if not rows:
        return []
    header = [h.lower() for h in cells(rows[0])]
    # Header wording drifts over time: Name / Place / Establishment / Facility Name,
    # Type / Tyle / Inspection_Type, and sometimes the type is split across two columns.
    def find(*words, default=None):
        return next((i for i, h in enumerate(header) if any(w in h for w in words)), default)
    i_name = find("name", "place", "establishment", "facility", default=0)
    i_score = find("score")
    i_addr = find("address", "location")  # a few July 2024 posts have no address column at all
    i_date = find("date", default=len(header) - 1)
    if i_score is None or i_date <= max(i_score, i_addr or 0):
        return []
    out = []
    for tr in rows[1:]:
        c = cells(tr)
        if len(c) <= i_date or not any(c):
            continue
        if i_addr is None:
            addr = ("", "", "")
        else:
            addr = parse_address(c[i_addr])
            if not addr:
                print(f"  skip (address): {c}", file=sys.stderr)
                continue
        score, result = parse_score(c[i_score])
        type_cells = [x for i, x in enumerate(c) if max(i_score, i_addr or 0) < i < i_date and x]
        fac, itype = parse_type(" ".join(type_cells))
        fac = fac or default_facility  # pool-only and food-only posts sometimes drop the Type column
        out.append({
            "name": c[i_name].strip(), "score": score, "result_text": result,
            "street": addr[0], "city": addr[1], "zip": addr[2],
            "facility_type": fac, "inspection_type": itype, "date": parse_date(c[i_date]),
            "source_url": source_url,
        })
    return out


def parse_stacked_table(table, source_url):
    """Single-column layout used in 2024: name / address / 'type | itype' / 'date | score' / View."""
    lines = [c[0] for c in (cells(tr) for tr in table.find_all("tr")) if c]
    out = []
    for i, line in enumerate(lines):
        if not ADDR_LOOKS.search(line) or i == 0 or i + 2 >= len(lines):
            continue
        addr = parse_address(line)
        if not addr:
            print(f"  skip (address): {line}", file=sys.stderr)
            continue
        name = lines[i - 1]
        fac, itype = parse_type(lines[i + 1])
        date_part, _, score_part = lines[i + 2].partition("|")
        score, result = parse_score(score_part)
        out.append({
            "name": name.strip(), "score": score, "result_text": result,
            "street": addr[0], "city": addr[1], "zip": addr[2],
            "facility_type": fac, "inspection_type": itype, "date": parse_date(date_part),
            "source_url": source_url,
        })
    return out


def facility_from_title(title):
    t = (title or "").lower()
    if "pool" in t:
        return "Swimming Pools"
    if "food" in t:
        return "Food Service"
    return ""


def parse_post(content_html, source_url, title=""):
    soup = BeautifulSoup(content_html, "html.parser")
    records = []
    for table in soup.find_all("table"):
        first = cells(table.find("tr")) if table.find("tr") else []
        if len(first) >= 4:
            records += parse_wide_table(table, source_url, facility_from_title(title))
        elif len(first) == 1:
            records += parse_stacked_table(table, source_url)
    return [r for r in records if r["name"] and r["date"]]


# ---------------------------------------------------------------- main

def load_seen():
    if POSTS_SEEN.exists():
        return json.loads(POSTS_SEEN.read_text(encoding="utf-8"))
    return {}


def save_seen(seen):
    POSTS_SEEN.parent.mkdir(parents=True, exist_ok=True)
    ordered = dict(sorted(seen.items(), key=lambda kv: kv[1].get("post_date", ""), reverse=True))
    POSTS_SEEN.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="re-parse every post, not just unseen ones")
    ap.add_argument("--primary-only", action="store_true", help="ignore lowest/perfect roundup posts")
    args = ap.parse_args()

    print("Discovering posts via the WordPress REST API...")
    posts = discover_posts()
    if args.primary_only:
        posts = {u: p for u, p in posts.items() if p["kind"] == "primary"}
    n_primary = sum(p["kind"] == "primary" for p in posts.values())
    print(f"  {len(posts)} matching posts ({n_primary} weekly roundups, {len(posts) - n_primary} secondary)")

    seen = load_seen()
    existing = read_inspections()
    index = {dedupe_key(r): r for r in existing}
    todo = sorted(
        (u for u in posts if args.all or u not in seen),
        key=lambda u: posts[u]["date"],
    )
    print(f"  {len(todo)} posts to parse")

    new_rows = 0
    # Primary posts first so a duplicate row keeps the weekly roundup as its source_url.
    for url in sorted(todo, key=lambda u: (posts[u]["kind"] != "primary", posts[u]["date"])):
        p = posts[url]
        try:
            content = fetch_post_html(url, p["id"])
            rows = parse_post(content, url, p["title"])
        except Exception as e:  # keep going; the post stays unseen and is retried next run
            print(f"  FAILED {url}: {e}", file=sys.stderr)
            continue
        added = 0
        for r in rows:
            k = dedupe_key(r)
            if k not in index:
                index[k] = {**r, "lat": "", "lon": "", "geo_source": "", "geo_precision": ""}
                added += 1
        new_rows += added
        seen[url] = {
            "post_id": p["id"], "title": p["title"], "post_date": p["date"], "kind": p["kind"],
            "rows_in_table": len(rows), "rows_added": added,
            "scraped_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        print(f"  {p['date']}  {len(rows):>3} rows  +{added:<3}  {p['title']}")

    write_inspections(sort_rows(index.values()))
    save_seen(seen)

    if unknown_cities:
        print("\nCities not in CITY_ALIASES (check spelling, then add to scripts/common.py):", file=sys.stderr)
        for c, sample in unknown_cities.items():
            print(f"  {c!r}  e.g. {sample}", file=sys.stderr)

    print(f"\nDone: {new_rows} new inspections, {len(index)} total in data/inspections.csv")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"new_inspections={new_rows}\n")


if __name__ == "__main__":
    main()
