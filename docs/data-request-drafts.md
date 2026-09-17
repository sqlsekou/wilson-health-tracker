# Getting the inspection data the right way

Two emails to send the same day, plus a phone call. Fill in the bracketed parts.

## Who to contact

| Door | Contact | Why |
|---|---|---|
| Wilson County Health Department, Environmental Health | (615) 444-5325, 927 E. Baddour Pkwy, Lebanon, TN 37087 | The local specialists who do the inspections. Ask who at the state handles data exports. |
| TDH Environmental Health Program | Geh.health@tn.gov, (615) 741-7206 | Owns the program and the HealthSpace portal contract. Informal ask for an export or feed. |
| TDH Public Records Request Coordinator | Health.PRRC@tn.gov, Andrew Johnson Tower, 5th Floor, 710 James Robertson Pkwy, Nashville, TN 37243, fax (615) 532-7668 | Formal request under the Tennessee Public Records Act. Seven business days to respond. |

The formal request must include your full name, street address, email, and a copy of a Tennessee government-issued ID (the Act limits requests to Tennessee citizens).

## Email 1: informal ask to the program office

**To:** Geh.health@tn.gov
**Subject:** Wilson County inspection data export for a public tracker

Hello,

My name is Sekou Tyler. I run Royal Blue Analytics, a data analytics practice in Nashville. I built a free public dashboard that lets Wilson County residents look up a restaurant, pool, hotel, or child care facility and see its inspection history: https://sqlsekou.github.io/wilson-health-tracker/

Right now the data comes from the weekly health score tables that Wilson County Source publishes, which are drawn from your inspection portal. Comparing the two, I found the newspaper tables run about two weeks behind the portal and leave out a routine score when a follow-up happens the same day. I would rather show residents the record straight from the department.

Is there a way to get a periodic export of Wilson County inspection results, or a data feed from the portal (inspections.myhealthdepartment.com/tennessee)? The fields I am after are the ones already shown publicly on the portal:

- establishment name, address, city, zip, permit ID and permit type
- inspection ID, date, program, purpose (routine, follow-up, complaint), score or recommendation
- inspector comments if they are considered public

A weekly CSV or a scheduled export covering Wilson County from January 2024 forward would be ideal. If the HealthSpace portal has a data-sharing option, I would be glad to talk with whoever manages that contract.

The dashboard credits the Tennessee Department of Health as the source of every score and links each establishment back to the portal. Happy to walk you through it or adjust anything you would want changed.

Thank you,
Sekou Tyler
Founder, Royal Blue Analytics
[phone]
https://royalblueanalytics.com

## Email 2: formal public records request

**To:** Health.PRRC@tn.gov
**Subject:** Public records request: Wilson County environmental health inspection results
**Attach:** copy of Tennessee driver's license

To the Public Records Request Coordinator,

Under the Tennessee Public Records Act, T.C.A. 10-7-503, I request copies of the following public records held by the Department of Health, Environmental Health Program.

Records requested: environmental health inspection results for establishments in Wilson County, Tennessee, from January 1, 2024 through the date of your response, for all programs displayed on the department's public inspection portal (food service establishments, public swimming pools, hotels and motels, child care facilities, school buildings, tattoo and body piercing studios, campgrounds, and bed and breakfasts).

For each inspection, the fields displayed on the public portal at inspections.myhealthdepartment.com/tennessee: establishment name, street address, city, zip, permit ID, permit type, program name and code, inspection ID, inspection date, inspection purpose, score or recommendation, and inspector comments.

Format: electronic, as CSV or Excel, delivered by email to [email]. I am not requesting paper copies. If the records exist in a database, an export of the relevant fields is preferred over printed reports.

Ongoing access: if the department is able to provide this export on a recurring basis (weekly or monthly), please let me know the process for arranging that.

If any portion of this request is denied, please cite the specific exemption and release the remaining records. If the cost of producing these records will exceed $25, please contact me before proceeding.

Requester information:
Name: Sekou Tyler
Address: [street address, city, TN zip]
Email: [email]
Phone: [phone]
Tennessee citizenship: a copy of my Tennessee driver's license is attached.

Thank you for your assistance.

Sekou Tyler

## Phone script for the local office

"Hi, I'm looking for Environmental Health. I built a free public website that tracks Wilson County health inspection scores, and I'd like to get the data directly from the department instead of from the newspaper. Who at the state should I talk to about a data export from the inspection portal?"

Write down the name they give you and add it to Email 1 as a cc.

## After a yes

The pipeline needs one new script, scripts/scrape_tdh.py, that reads the export and writes the same columns as scrape.py. The dedupe key moves to permit ID plus inspection ID. Everything downstream (geocode, build, dashboard, weekly workflow) stays as it is.
