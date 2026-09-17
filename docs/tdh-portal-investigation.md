# TDH inspection portal: investigation notes

Date: September 17, 2026. Investigated by watching what the portal's own page does in a normal browser and reading the JavaScript it loads. No scripted requests were made against the portal.

## Why this matters

The dashboard mirrors the weekly Health Scores tables from Wilson County Source. Checking Shoney's #226 (820 S. Cumberland, Lebanon) against the state portal showed two gaps in that mirror:

1. **Lag.** The paper printed a 59 (routine, September 10). The portal already had a 93 follow-up on September 16, two days after the paper's post. The paper will carry it in the next post, so the dashboard runs up to two weeks behind the state.
2. **Omission.** When a routine inspection and its follow-up land on the same day, the paper prints only the follow-up. TDH shows Shoney's with a 94 routine and a 99 follow-up on March 13, 2026; the paper printed only the 99. Over the same window TDH lists 9 inspections for this one restaurant and the paper's tables yield 6.

Neither is an error by the paper. Their tables are "most recent score" snapshots. But it means the newspaper copy is a lagging, lossy version of the state record.

## How the portal works

- Front end: Webflow page with jQuery controllers. Back end: HealthSpace Cloud Suite (services-api.hscloudsuite.com). Vendor product name: My Health Department.
- Data is not in the HTML. The page calls one JSON RPC endpoint and renders the result client-side.
- No public API, feed, export, terms page, or contact is published.

### The endpoint the page uses

```
POST https://inspections.myhealthdepartment.com/
Content-Type: application/json

{
  "task": "searchInspections",
  "data": {
    "path": "tennessee",
    "programName": "",
    "filters": { "date": "YYYY-MM-DD to YYYY-MM-DD", "purpose": "", "county": "Wilson" },
    "start": 0,
    "count": 20,
    "searchQueryOverride": null,
    "searchStr": "",
    "lat": 0, "lng": 0,
    "sort": {}
  }
}
```

- Filters come from the three form controls: date range, purpose (Routine, Complete, Follow-Up, Complaint), county.
- Pagination is offset based: `start` and `count`. "Load more" adds `count` to `start`.
- Other tasks seen: jurisdiction config, API URL config, `getPrintable` (PDF of one inspection).
- Establishment history: `/tennessee/permit/?permitID=...`. Inspection detail with observations: `/tennessee/inspection/?inspectionID=...`.

### Fields returned per inspection

```
inspectionID, inspectionDate, purpose, inspectionType, programName, programCode,
score, recommendation, scoreDisplay, comments, timein,
establishmentName, addressLine1, addressLine2, city, state, zip,
permitID, permitType
```

Three of these are not in the newspaper tables and would improve the dashboard directly: `permitID` (a stable establishment key, which replaces name-spelling dedupe), `comments` (inspector narrative), and `permitType` / `programCode` (real categories).

### Scale for Wilson County

Roughly 2,200 inspections a year. A full pull from January 2024 is under 6,000 rows, about 30 requests at `count=200`. A weekly refresh with a date filter is one request.

## Why the pipeline does not call this endpoint

The portal refuses scripted access in three ways:

1. `robots.txt` is `User-agent: * / Disallow: /`. Every automated agent is blocked, with named blocks for AI crawlers. Googlebot and Bingbot are allowed only the home page.
2. The server returns HTTP 403 to any client whose User-Agent is not a browser. The pipeline's honest User-Agent is rejected.
3. A reCAPTCHA gate for search is built into the page and currently switched off for Tennessee (`enableCaptchaInspectionsLandingPage: false`). The vendor can enable it at any time.

The only way a script gets through is by claiming to be a browser. That is evading a control the operator built specifically to stop scripted access, so it is out of scope for this project. The Virginia civic-tech scraper built against this same platform (Code4HR open-health-inspection-api) is the cautionary example: it worked until the site changed.

## The correct path

Ask for the data. See `data-request-drafts.md` for the contacts, the informal ask to the Environmental Health Program, and the formal request under the Tennessee Public Records Act. Wilson County is small enough that an export is a routine request, and an official source is worth more to the project than a scraper.

When an export or feed arrives, add `scripts/scrape_tdh.py` producing the same columns as `scrape.py`, move the dedupe key to `permitID` + `inspectionID`, and leave the rest of the pipeline alone.
