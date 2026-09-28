# PI GURBANI REALESTATE

Enter an Indian city in the browser interface, search residential project candidates, preview results and download Excel. Runs locally on this Windows computer; no coding is needed for day-to-day use.

## Windows quick start

1. Install Python 3.10 or newer from https://www.python.org/downloads/ if needed. Enable "Add Python to PATH" during installation.
2. On GitHub, select **Code > Download ZIP**, then extract it completely.
3. Open the extracted folder. Copy `.env.example` to `.env` and replace the placeholder with your Google Places API key. Enable Places API (New) and billing for that key. This is a one-time administrator setup. Double-click `run_windows.bat`.
4. The launcher creates a local virtual environment and installs dependencies (internet required).
5. The browser opens PI GURBANI REALESTATE. The backend loads the key from `.env` beside `main.py`; the key is never sent to the browser.
6. Type a city, click **Find projects**, then **Download Excel**. Reports are also saved in `output` with city and timestamp in the filename.

Keep the launcher window open while using the app. Closing it stops the local server. This is a local application, not a deployed public website. The existing `python main.py` command still exports Mumbai directly.

City searches use Google Places. Detailed saved research is joined by exact Place ID and currently mainly covers Mumbai. Magicbricks and 99acres are not queried live. New cities can have blank prices, RERA, units and possession fields until project research is added. Returned candidates can include agencies and nearby cities; this is not an exhaustive city inventory.

Your Google Cloud project must have Places API (New) enabled, billing configured, and a key whose restrictions permit these web-service requests. API usage may incur charges. Your local `.env` file is excluded from Git; do not share it.

## Manual setup (any platform)

Run these commands inside the extracted project folder:

```sh
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or activate on macOS/Linux:

```sh
source .venv/bin/activate
```

Then:

```sh
python -m pip install -r requirements.txt
python main.py
```

The script checks the `GOOGLE_MAPS_API_KEY` environment variable first, then `.env`, then prompts privately. To configure `.env`, add `GOOGLE_MAPS_API_KEY=your_key_here`. Do not commit or share your key.

## Excel columns

The `Projects` sheet includes Project Name, Brand Name, Builder Name, Latitude, Longitude, Address, City, Locality, Status, Project Overview, Highlights, Launch Date, Possession Date, Configurations Type, RERA (Registration No), Number of Towers, Number of Units, Total Project Area (Acres), Last Updated Date, Approved Banks and Amenities. Source identifiers, contact links, search category and retrieval time follow these columns.

The `Project Units` sheet supports multiple configurations per project: Place ID, Project Name, Cat ID, Unit Type, Area (Sq Ft), Price (Rs.), Area Basis, Source URL, Source Updated Date and Price / Configuration Notes. Saved research provides configurations and advertised prices where found. Cat ID is blank when the property source does not provide it.

Google supplies names, coordinates, address components and contact details where available. `project_details.json` contains research checked on 28 September 2026, joined by exact Google Place ID. It covers 53 researched rows, 37 likely non-project listings and 10 unresolved records from the original 100-candidate export. New Google results without a matching record remain marked Not researched. The file is a research snapshot, not an automatic web scraper or a live price feed.

Projects includes Record Review, Detail Source URL, Research Checked Date, Research Notes and Missing Project Fields. Filter Record Review to distinguish researched projects from company/agency listings. Portal claims are attributed, not independently certified against MahaRERA. Conflicts, old possession targets and phase-specific information are flagged. Prices and areas are paired only where the source supports that pairing; ranges remain in notes. Missing numeric values remain blank rather than zero. Last Updated Date is the source's own date, never the script run date. Month-only dates remain text to avoid inventing a day.

The script follows pagination and combines duplicate place IDs across the two searches. Empty API fields remain blank. Failed searches stop before writing a new workbook; previously saved workbooks remain available.

## What the results mean

- These are candidates returned by text search, not a complete Mumbai project database. Agencies, unrelated places and nearby locations may be returned.
- Search categories describe the queries, not verified project status. All statuses start as "Needs verification".
- Places does not supply property listing-added dates, project launch dates or possession dates. Date columns remain blank for verification from project-specific sources. The script does not filter recently added projects.
- Prices, developer identity and ready-to-move status from saved research need reconfirmation with the developer or regulator. Research sources are linked in the workbook.
- No live API data is bundled. Run with your own compatible key to retrieve results.
- Google restricts storage/export of Places content. Review the applicable terms before exporting or retaining returned content: https://developers.google.com/maps/documentation/places/web-service/policies

API reference: https://developers.google.com/maps/documentation/places/web-service/text-search

## Troubleshooting

- HTTP 400: verify the request and that you are using Places API (New).
- HTTP 401/403: check the key, API enablement, billing and key restrictions.
- HTTP 429: check project quota and billing; retry later.
- Network failure: check your internet connection and retry.
- Permission error saving Excel: check folder permissions and close any workbook that could be locked.

## Folder layout

```text
mumbai-realestate-project/
  main.py
  requirements.txt
  run_windows.bat
  README.md
  .gitignore
  output/
    README.txt
```
