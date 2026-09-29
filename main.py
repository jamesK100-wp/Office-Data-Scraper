"""Find candidate projects on Magicbricks and 99acres.
Install: python -m pip install requests openpyxl
Run: python main.py
No Google API key required. Portal access and published details vary.
"""
import os
import json
import sys
from getpass import getpass
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from enrichment import enrich

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
    "Automatic Research Status", "Automatic Research Date",
]
UNIT_COLUMNS = ["Place ID", "Project Name", "Cat ID", "Unit Type", "Area (Sq Ft)",
                "Price (Rs.)", "Area Basis", "Source URL", "Source Updated Date",
                "Price / Configuration Notes", "Number of Units", "Total Project Area (Acres)",
                "Last Updated Date", "Approved Banks", "Amenities"]


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
    fields = detail.get("fields", {})
    return [["" if pid.startswith("http") else pid, name, "", kind, area, price, basis, detail.get("unit_source", detail.get("source", "")),
             source_date(detail.get("unit_updated", fields.get("Last Updated Date", ""))), note,
             fields.get("Number of Units"), fields.get("Total Project Area (Acres)"),
             source_date(fields.get("Last Updated Date", "")),
             fields.get("Approved Banks", ""), fields.get("Amenities", "")]
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
        "Place ID": "" if pid.startswith("http") else pid,
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
        "Automatic Research Status": detail.get("auto_status", "Not checked"),
        "Automatic Research Date": source_date(detail.get("auto_checked", "")),
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


def main(city="Mumbai", interactive=True, auto_research=True, progress=None):
    city = " ".join(city.split())
    if not 2 <= len(city) <= 80 or not all(c.isalpha() or c in " ,.-'" for c in city):
        raise ValueError("Enter a city name, optionally followed by its Indian state.")
    from portals import discover
    candidates, details, source_reports = discover(city, progress)
    if not candidates:
        raise ValueError(' '.join(source_reports) + ' No accessible project records returned. No empty workbook created.')
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
        'Sources restricted to Magicbricks and 99acres. No Google or saved third-party research is used.',
        f'Search city: {city}. First directory page per portal, up to 30 project pages per portal; not exhaustive.',
        'Source URLs identify records. Google Place ID and Cat ID are not invented.',
        'Missing numeric details stay blank. Automatic Research Status explains extraction limits.',
        'Portal overview values may describe different project phases; totals need verification.',
        'Unit records require supported structured floor plans. No prices, banks or availability are inferred.',
        *source_reports,
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
    return {"sources": source_reports, "file": target.name, "count": len(candidates),
            "researched": sum(bool(details.get(pid, {}).get("fields")) for pid in candidates),
            "units": units.max_row - 1,
            "preview": [{"name": e["place"].get("displayName", {}).get("text", ""),
                         "address": e["place"].get("formattedAddress", "")}
                        for e in list(candidates.values())[:10]]}


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit(str(exc))
    except requests.RequestException:
        raise SystemExit("Network request failed. Check your connection and retry.")
    except OSError:
        raise SystemExit("Could not read configuration or save the workbook. Check folder permissions and close any locked output file.")
