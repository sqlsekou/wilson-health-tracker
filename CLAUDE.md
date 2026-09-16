# Wilson County Health Inspection Tracker

Project owner: Sekou Tyler, Founder & CEO, Royal Blue Analytics
Website: https://royalblueanalytics.com · LinkedIn: https://www.linkedin.com/in/sekoutyler/

## What this project is

A public, embeddable web dashboard that turns the recurring "Health Scores Wilson County" posts from Wilson County Source (https://wilsoncountysource.com) into a searchable, mapped tracker. It is a portfolio piece for sqlsekou.com and a business development pitch to partner with Wilson County Source (and its sister Source sites) on data analytics.

The dashboard is a single static `index.html` hosted on GitHub Pages and embedded in WordPress with an iframe. A scheduled job scrapes new posts, geocodes new addresses, rebuilds the data file, and pushes to GitHub.

## Goals, in order

1. Get the current dashboard live on GitHub Pages.
2. Split the embedded data out of `index.html` into `data/inspections.json`.
3. Build the scraper so every health score post (current and historical) lands in one dataset.
4. Geocode addresses once and store the coordinates in the data file.
5. Schedule a weekly refresh that commits and deploys automatically.
6. Phase 2: score history per establishment, repeat low scorer flags.

## Repo structure (target)

```
wilson-health-tracker/
├── CLAUDE.md
├── README.md
├── index.html                  # the dashboard (static, no build step)
├── data/
│   ├── inspections.json        # dashboard data, generated
│   ├── inspections.csv         # same data for humans and Power BI/Tableau
│   ├── geocode_cache.csv       # address -> lat/lon, never regenerate from scratch
│   └── posts_seen.json         # source post URLs already processed
├── scripts/
│   ├── scrape.py               # find and parse health score posts
│   ├── geocode.py              # Census batch geocoder + Nominatim fallback
│   └── build.py                # merge, clean, write json/csv
├── requirements.txt
└── .github/workflows/refresh.yml
```

## Starting files

These were built in Claude chat and should be copied into the repo first:

- `wilson-county-health-dashboard.html` → rename to `index.html`
- `wilson_county_health_scores_2026-09-14.csv` → `data/inspections.csv` (72 rows, Sept 2 to 14, 2026)
- `geocode.py` → `scripts/geocode.py`

## Data source

- Post URL pattern: `https://wilsoncountysource.com/health-scores-wilson-county-for-<month>-<day>-<year>/`
  Example: https://wilsoncountysource.com/health-scores-wilson-county-for-september-14-2026/
- The site runs WordPress. Try the REST API first to discover posts, for example
  `https://wilsoncountysource.com/wp-json/wp/v2/posts?search=health%20scores&per_page=100`.
  Verify this works before relying on it. Fall back to the site search page or the category archive if the API is disabled.
- There may also be separate "lowest food health scores" roundup posts. Treat those as a secondary source and dedupe against the main table.
- Each post contains one HTML table with columns: Name, Score, Address, Type, Date.
- Underlying data is Tennessee Department of Health inspections. Credit both TDH and Wilson County Source everywhere the data appears.
- Be polite: identify with a clear User-Agent, cache pages, and do not hammer the site. One request per second is plenty.

## Data model

One row per inspection. The dashboard's JS expects each record as an array in this exact order:

```
[name, score, result_text, street, city, zip, facility_type, inspection_type, date, lat, lon]
```

| Field | Notes |
|---|---|
| name | As published |
| score | Integer 0 to 100, or `null` when not numeric |
| result_text | Non-numeric result such as "Approval", else empty string |
| street | Street portion of the address |
| city | Normalize "Mt Juliet" and "Mt.Juliet" to "Mt. Juliet" |
| zip | 5-digit string |
| facility_type | Split from Type: Food Service, Swimming Pools, Child Care Facilities, Tattoo Studios, School Buildings, etc. |
| inspection_type | Routine or Follow-Up |
| date | ISO `YYYY-MM-DD` |
| lat, lon | Floats, or `null` if unmatched |

Dedupe key: name + street + date + inspection_type.
The CSV should carry the same fields with headers plus `source_url`, `geo_source`, and `geo_precision`.

## Parsing rules

- Address format is `<street> <city> TN <zip>`. Cities seen so far: Mt. Juliet, Lebanon, Old Hickory, Watertown. Expect others in Wilson County.
- Type format is `<facility type> <Routine|Follow-Up>`.
- Blank scores stay `null`. "Approval" goes to `result_text`.
- A score of 0 on a follow-up (seen on a pool) is kept as published but should be checked. It may represent a closure.

## Geocoding rules

- Primary: US Census batch geocoder, `https://geocoding.geo.census.gov/geocoder/locations/addressbatch`, benchmark `Public_AR_Current`. Free, no key, public domain.
- Fallback: OpenStreetMap Nominatim, max 1 request per second, custom User-Agent required.
- Last resort: city/zip centroid, labeled `geo_precision = city centroid`.
- Clean before geocoding: split number from street ("100Reunion" → "100 Reunion"), drop suites ("STE 210", "Ste 500"), drop trailing unit numbers ("Rd 102"), fix "Mt.Juliet".
- Always read and update `data/geocode_cache.csv`. Only geocode addresses not already cached.
- Do not use Google Maps or Google Places coordinates. Their terms do not allow storing them in this dataset.
- Known tough addresses: "Hillview Farms Subdivision", "Heatherly Wy" (no street number). Several facilities share 1100 Dell Webb Blvd; the map groups them into one pin.

## Dashboard (index.html)

- Static HTML, CSS, and vanilla JS. Leaflet 1.9.4 from cdnjs. OpenStreetMap tiles. No build step, no framework.
- Layout top to bottom: royal blue header with RBA badge, City and Type filter pills, 4 KPI cards (Inspections, Average Score, Perfect 100s, Scored Below 80), 3 charts (Score Distribution, Lowest Scores, Average by City), map and Find a Business table side by side, footer with Website / LinkedIn / Book a discovery call, "About this data" dropdown.
- Clicking a table row zooms the map to that pin.
- Map uses stored lat/lon first. It only falls back to live Nominatim lookups in the browser when coordinates are missing. Once the pipeline stores coordinates, that fallback should rarely run.
- Posts its height to the parent window (`{type: 'wchs-height', height}`) for auto-resizing iframes.
- When moving data out of the HTML, replace the inline `const DATA = [...]` with a `fetch('data/inspections.json')` and render after it loads. Show a simple loading state.
- Supports light and dark mode through CSS variables.

## Branding and writing style

- Accent color: Royal Blue `#253B8E`. Score colors: green `#2E7D52` (90+), amber `#B7791F` (70 to 89), red `#CC0000` (under 70).
- Font: Segoe UI with system fallbacks. Left-aligned text.
- Every page shows "Created by Royal Blue Analytics" in the header and footer. Discovery call link: https://calendly.com/sekoutyler/discovery
- Label it an independent demo. Do not imply a partnership with Wilson County Source until one exists.
- No em dashes anywhere in UI text, README, commit messages, or docs.
- Copy should read naturally, not like AI-generated text.

## Scheduled refresh

Preferred: a GitHub Actions workflow, so the refresh runs even when Sekou's computer is off.

- Trigger: weekly cron (Tuesday morning Central works well since posts land around Monday), plus `workflow_dispatch` for manual runs.
- Steps: checkout, set up Python, `pip install -r requirements.txt`, run `scrape.py` → `geocode.py` → `build.py`, commit changed files in `data/` only if something changed, push. GitHub Pages redeploys automatically.
- Commit message format: `Data refresh: <N> new inspections through <latest date>`
- Give the workflow `contents: write` permission. Never hardcode tokens; use the built-in `GITHUB_TOKEN`.

A Claude Code scheduled trigger can be used instead or in addition, for example to review the refresh, flag unusual scores, or draft a short weekly summary. Check the current Claude Code docs for how scheduling works before setting it up.

## Hosting

- GitHub repo: `wilson-health-tracker`, public.
- GitHub Pages: deploy from `main`, root folder.
- Optional custom domain: `demos.sqlsekou.com` via a CNAME record pointing to `<username>.github.io`. Enforce HTTPS.
- If this becomes a paid engagement, move hosting to Cloudflare Pages, Netlify, or the client's hosting. GitHub Pages is not meant for commercial sites.

## WordPress embed

```html
<iframe id="wchs" src="https://YOUR-HOSTED-URL/" width="100%" height="800"
  style="border:0;" loading="lazy" title="Wilson County Health Inspection Tracker"></iframe>
<script>
window.addEventListener('message', function (e) {
  if (e.data && e.data.type === 'wchs-height') {
    document.getElementById('wchs').style.height = e.data.height + 'px';
  }
});
</script>
```

## Guardrails

- Ask before creating the public repo, changing repo settings, or pushing for the first time.
- Never commit secrets. Keep `.env` in `.gitignore`.
- Keep the data honest: never estimate or invent coordinates or scores. Unmatched stays `null`.
- Do not scrape anything behind a login.
- Test the dashboard locally (`python -m http.server`) before pushing layout changes, on both desktop and a narrow mobile width.

## Business context

- Pitch contact options from the Wilson County Source contact page: news@wilsoncountysource.com, info@wilsoncountysource.com, advertising contact marylee.bennett@empowerlocal.com, (615) 237-8600.
- Pitch angle: the paper publishes static tables that go stale. A running tracker drives return visits, gives the newsroom automatic story leads (repeat low scorers, closures), and one data model can scale to the other Source county sites.
- Planned content: a build story blog post on sqlsekou.com with the live dashboard embedded, cross-posted to LinkedIn and Substack.
