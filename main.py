"""Find candidate Mumbai projects. Status and launch dates require verification.
Install: python -m pip install requests openpyxl
Run: python main.py
Requires Google Places API (New) enabled and billing configured.
Review Google's Places storage terms before exporting/retaining API content.
"""
import os
import json
from getpass import getpass
from datetime import datetime, timezone
from pathlib import Path

import requests
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


PROJECT_COLUMNS = [
    "Project Name", "Brand Name", "Builder Name", "Latitude", "Longitude",
    "Address", "City", "Locality", "Status", "Project Overview", "Highlights",
    "Launch Date", "Possession Date", "Configurations Type",
    "RERA (Registration No)", "Number of Towers", "Number of Units",
    "Total Project Area (Acres)", "Last Updated Date", "Approved Banks", "Amenities",
    "Place ID", "Phone", "Website", "Google Maps link",
    "Search category (unverified)", "Retrieved at (UTC)",
    "Record Review", "Detail Source URL", "Research Checked Date", "Research Notes",
    "Missing Project Fields",
]
UNIT_COLUMNS = ["Place ID", "Project Name", "Cat ID", "Unit Type", "Area (Sq Ft)",
                "Price (Rs.)", "Area Basis", "Source URL", "Source Updated Date",
                "Price / Configuration Notes"]


def load_project_details():
    path = Path(__file__).resolve().parent / "project_details.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise SystemExit("project_details.json is invalid. Correct its JSON before running.")
    if not isinstance(data, dict) or any(not isinstance(v, dict) for v in data.values()):
        raise SystemExit("project_details.json must map Google Place IDs to detail records.")
    return data


def source_date(value):
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            pass
    return value


def project_units(pid, name, detail):
    return [[pid, name, "", kind, area, price, basis, detail.get("source", ""),
             source_date(detail.get("fields", {}).get("Last Updated Date", "")), note]
            for kind, area, price, basis, note in detail.get("units", [])]


def address_component(place, *types):
    for kind in types:
        for component in place.get("addressComponents", []):
            if kind in component.get("types", []):
                return component.get("longText", "")
    return ""


def project_row(pid, entry, retrieved, detail=None):
    place = entry["place"]
    location = place.get("location", {})
    values = {
        "Project Name": place.get("displayName", {}).get("text", ""),
        "Latitude": location.get("latitude"),
        "Longitude": location.get("longitude"),
        "Address": place.get("formattedAddress", ""),
        "City": address_component(place, "locality"),
        "Locality": address_component(place, "sublocality_level_1", "sublocality", "neighborhood"),
        "Status": "Needs verification",
        "Place ID": pid,
        "Phone": place.get("nationalPhoneNumber", ""),
        "Website": place.get("websiteUri", ""),
        "Google Maps link": place.get("googleMapsUri", ""),
        "Search category (unverified)": "; ".join(sorted(entry["queries"])),
        "Retrieved at (UTC)": retrieved,
    }
    detail = detail or {}
    # Only the researched project fields are overlaid; original identity stays intact.
    for column, value in detail.get("fields", {}).items():
        if column in PROJECT_COLUMNS[1:21] and column not in ("Latitude", "Longitude", "Address", "City", "Locality"):
            values[column] = value
    values.update({
        "Record Review": detail.get("review", "Not researched"),
        "Detail Source URL": detail.get("source", ""),
        "Research Checked Date": source_date(detail.get("checked", "")),
        "Research Notes": detail.get("notes", "No research record for this Google Place ID."),
        "Missing Project Fields": "; ".join(c for c in PROJECT_COLUMNS[1:21] if values.get(c) in (None, "")),
    })
    values["Last Updated Date"] = source_date(values.get("Last Updated Date", ""))
    return [values.get(column, "") for column in PROJECT_COLUMNS]


def format_table(sheet):
    sheet.freeze_panes = "C2"
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="17365D")
        sheet.column_dimensions[get_column_letter(cell.column)].width = max(22, len(cell.value) + 3)
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            # External strings must remain literal text, never executable formulas.
            if isinstance(cell.value, str):
                cell.data_type = "s"
            if sheet.cell(1, cell.column).value in ("Latitude", "Longitude"):
                cell.number_format = "0.00000"
            elif isinstance(cell.value, datetime):
                cell.number_format = "dd/mm/yyyy"
            elif sheet.cell(1, cell.column).value == "Price (Rs.)":
                cell.number_format = '"Rs "#,##0'


def load_api_key(interactive=True):
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    config = Path(__file__).resolve().parent / ".env"
    if not key and config.is_file():
        for line in config.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.strip().partition("=")
            if separator and name.strip() == "GOOGLE_MAPS_API_KEY":
                key = value.strip().strip("\"'")
                break
    if not key and not interactive:
        raise ValueError("API key is missing. Ask the administrator to configure the .env file.")
    if not key:
        try:
            key = getpass("Google API key (hidden): ").strip()
        except EOFError:
            raise SystemExit("Set GOOGLE_MAPS_API_KEY in the .env file beside main.py.")
    return key


def main(city="Mumbai", interactive=True):
    city = " ".join(city.split())
    if not 2 <= len(city) <= 80 or not all(c.isalpha() or c in " ,.-'" for c in city):
        raise ValueError("Enter a city name, optionally followed by its Indian state.")
    details = load_project_details()
    key = load_api_key(interactive)
    if not key.strip():
        raise SystemExit("An API key is required.")
    headers = {
        "X-Goog-Api-Key": key.strip(),
        "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,"
        "places.location,places.addressComponents,"
        "places.websiteUri,places.nationalPhoneNumber,places.googleMapsUri,nextPageToken",
    }
    candidates = {}
    # Query categories are search intent, NOT evidence of project status.
    for category in ("upcoming residential projects", "ready to move residential projects"):
        query = f"{category} in {city}, India"
        body = {"textQuery": query, "pageSize": 20, "languageCode": "en", "regionCode": "IN"}
        tokens = set()
        while True:
            response = requests.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers=headers, json=body, timeout=45,
            )
            if not response.ok:
                try:
                    detail = response.json().get("error", {}).get("message", "")
                except ValueError:
                    detail = ""
                detail = str(detail).replace(key, "[REDACTED]")
                raise SystemExit(
                    f"Google API request failed (HTTP {response.status_code}). "
                    f"{detail} "
                    "Check your key restrictions, Places API (New), billing and quota. "
                    "No new workbook was written."
                )
            try:
                data = response.json()
            except ValueError:
                raise SystemExit("Google returned an invalid JSON response. Please retry.")
            for place in data.get("places", []):
                pid = place.get("id")
                if not pid:
                    continue
                entry = candidates.setdefault(pid, {"place": place, "queries": set()})
                entry["queries"].add(category)
            token = data.get("nextPageToken")
            if not token:
                break
            if token in tokens:
                raise SystemExit("Repeated pagination token; stopped without writing a workbook.")
            tokens.add(token)
            body["pageToken"] = token

    wb = Workbook()
    sheet = wb.active
    sheet.title = "Projects"
    sheet.append(PROJECT_COLUMNS)
    retrieved = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    for pid, entry in candidates.items():
        sheet.append(project_row(pid, entry, retrieved, details.get(pid)))
    format_table(sheet)
    units = wb.create_sheet("Project Units")
    units.append(UNIT_COLUMNS)
    for pid, entry in candidates.items():
        for row in project_units(pid, entry["place"].get("displayName", {}).get("text", ""), details.get(pid, {})):
            units.append(row)
    format_table(units)
    notes = wb.create_sheet("Read me")
    for line in [
        "Source: Google Maps / Places API (New)",
        f"Search city: {city}, India. These are candidates, not an exhaustive or verified project list.",
        "Results may include agencies, unrelated places or nearby cities; review addresses.",
        "Search category does not confirm upcoming or ready-to-move status.",
        "Places does not provide project launch dates, possession dates or listing-added dates.",
        "Blank project fields require another source: builder, brand, RERA, dates, towers, units, area, banks and amenities.",
        "Project details and units are supplemented from project_details.json, matched by exact Google Place ID.",
        "This is saved research, not a live property feed. See source URLs, research dates and conflict notes.",
        "Prices are advertised, not confirmed offers. Ranges and phase scope appear in Price / Configuration Notes.",
        "Likely non-project listings are retained and flagged for review, not treated as housing projects.",
        "Cat ID belongs to the property data provider; it is not a Google Place ID.",
        "Area Basis should specify carpet, built-up or saleable when the source identifies it.",
        "Last Updated Date means the source's project update date; it is not the retrieval date.",
        "Retrieved at records this search, not when a project was added or launched.",
        "Verify project status, developer, prices and dates using project-specific sources.",
        "Review storage/export restrictions before retaining Google content:",
        "https://developers.google.com/maps/documentation/places/web-service/policies",
    ]:
        notes.append([line])
    notes.column_dimensions["A"].width = 115
    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_city = "".join(c if c.isalnum() else "_" for c in city)
    target = output_dir / f"PI GURBANI REALESTATE_{safe_city}_{datetime.now():%Y%m%d_%H%M%S_%f}.xlsx"
    wb.save(target)
    print(f"Saved {len(candidates)} candidate places to {target}")
    if not candidates:
        print("No matches returned. The workbook contains headers and notes only.")
    return {"file": target.name, "count": len(candidates),
            "researched": sum(bool(details.get(pid, {}).get("fields")) for pid in candidates),
            "units": units.max_row - 1,
            "preview": [{"name": e["place"].get("displayName", {}).get("text", ""),
                         "address": e["place"].get("formattedAddress", "")}
                        for e in list(candidates.values())[:10]]}


if __name__ == "__main__":
    try:
        main()
    except requests.RequestException:
        raise SystemExit("Network request failed. Check your connection and retry.")
    except OSError:
        raise SystemExit("Could not read configuration or save the workbook. Check folder permissions and close any locked output file.")
