#!/usr/bin/env python3
"""
UK Sponsor Finder Tool - Daily Auto-Update Script
GitHub Pages site: shanik3.github.io/uk-sponsor-tool
No Netlify needed - GitHub Actions commits updated HTML directly.
"""

import json
import csv
import io
import re
import requests
from datetime import datetime
from collections import defaultdict
from bs4 import BeautifulSoup

GOV_PAGE  = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
HTML_FILE = "index.html"

ROUTES = ["SW", "GBM", "CW", "CHW", "SU", "OTH"]

LONDON_BOROUGHS = {
    "London","City of London","Westminster","Camden","Islington","Hackney",
    "Tower Hamlets","Greenwich","Lewisham","Southwark","Lambeth","Wandsworth",
    "Hammersmith and Fulham","Fulham","Hammersmith","Ealing","Hounslow",
    "Richmond","Kingston","Merton","Sutton","Croydon","Bromley","Bexley",
    "Havering","Barking and Dagenham","Redbridge","Newham","Waltham Forest",
    "Haringey","Enfield","Barnet","Harrow","Hillingdon","Brent",
}
MANCHESTER_TOWNS = {
    "Manchester","Salford","Bolton","Oldham","Rochdale","Wigan","Stockport",
    "Trafford","Tameside","Bury","Altrincham","Sale","Cheadle","Stretford",
    "Eccles","Swinton","Leigh","Ashton-under-Lyne","Hyde","Stalybridge",
    "Middleton","Heywood","Radcliffe","Farnworth",
}
WEST_YORKSHIRE_TOWNS = {
    "Leeds","Bradford","Huddersfield","Wakefield","Halifax","Dewsbury",
    "Keighley","Batley","Morley","Pudsey","Castleford","Pontefract",
    "Normanton","Wetherby","Otley","Ilkley","Shipley","Bingley",
    "Sowerby Bridge","Brighouse","Cleckheaton","Mirfield","Ossett",
    "Horsforth","Garforth","Rothwell",
}


def get_csv_url():
    print("Finding latest CSV URL from gov.uk...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.5",
    }
    r = requests.get(GOV_PAGE, headers=headers, timeout=30)
    print(f"gov.uk status: {r.status_code}")
    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.endswith(".csv") and ("Worker" in href or "sponsor" in href.lower()):
            url = href if href.startswith("http") else "https://assets.publishing.service.gov.uk" + href
            print(f"Found CSV URL: {url}")
            return url

    # GOV.UK API fallback
    print("Trying GOV.UK API fallback...")
    api = "https://www.gov.uk/api/content/government/publications/register-of-licensed-sponsors-workers"
    r2 = requests.get(api, headers=headers, timeout=30)
    for detail in r2.json().get("details", {}).get("attachments", []):
        url = detail.get("url", "")
        if url.endswith(".csv"):
            print(f"Found CSV via API: {url}")
            return url

    raise ValueError("Could not find CSV URL — check gov.uk page structure")


def classify_region(town, county):
    t = (town or "").strip().title()
    c = (county or "").strip().title()
    if any(x in t or x in c for x in ["London","Greater London","Middlesex"]):
        return "London"
    if t in LONDON_BOROUGHS or c in LONDON_BOROUGHS:
        return "London"
    if any(x in t or x in c for x in ["Manchester","Lancashire","Salford"]):
        return "Manchester"
    if t in MANCHESTER_TOWNS:
        return "Manchester"
    if "West Yorkshire" in c or "West Yorkshire" in t:
        return "West Yorkshire"
    if t in WEST_YORKSHIRE_TOWNS:
        return "West Yorkshire"
    return "Other"


def build_data_structure(rows):
    raw = {r: defaultdict(lambda: defaultdict(lambda: {"c": 0, "s": []})) for r in ROUTES}

    for row in rows:
        org      = (row.get("Organisation Name") or "").strip()
        town     = (row.get("Town/City") or "").strip()
        county   = (row.get("County") or "").strip()
        rl       = (row.get("Route") or "").strip().lower()
        sub_tier = (row.get("Sub Tier") or "").strip()

        if "skilled worker" in rl:           rk = "SW"
        elif "global business mobility" in rl: rk = "GBM"
        elif "creative worker" in rl:         rk = "CW"
        elif "charity worker" in rl or "religious worker" in rl: rk = "CHW"
        elif "scale-up" in rl or "scale up" in rl: rk = "SU"
        else:                                 rk = "OTH"

        region   = classify_region(town, county)
        town_key = town.upper() if town else "UNKNOWN"
        code     = sub_tier[:2].upper() if sub_tier else "O"

        raw[rk][region][town_key]["c"] += 1
        raw[rk][region][town_key]["s"].append([org, county, code])

    out_data, out_totals = {}, {}
    for rk in ROUTES:
        out_data[rk] = {}
        route_total  = 0
        region_totals = {"London":0,"Manchester":0,"West Yorkshire":0,"Other":0}
        for region in ["London","Manchester","West Yorkshire","Other"]:
            towns = raw[rk].get(region, {})
            town_list = sorted(
                [{"n":tn,"c":info["c"],"s":info["s"]} for tn,info in towns.items()],
                key=lambda x: x["c"], reverse=True
            )
            out_data[rk][region] = town_list
            rc = sum(t["c"] for t in town_list)
            region_totals[region] = rc
            route_total += rc
        out_totals[rk] = {"total": route_total, "regions": region_totals}

    return out_data, out_totals


def update_html(data, totals, total_sponsors):
    print("Updating HTML file...")
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # Safe replacement using fixed string markers — no regex on JSON body
    A_obj    = {"data": data, "totals": totals}
    new_json = json.dumps(A_obj, ensure_ascii=False, separators=(",", ":"))
    new_block = f"const A={new_json}"

    BEFORE = "const A="
    AFTER  = ";\nconst D=A.data"

    idx_b = content.find(BEFORE)
    idx_a = content.find(AFTER)

    if idx_b == -1 or idx_a == -1:
        # Fallback: find const D= and replace everything from const A= up to it
        idx_b = content.find("const A=")
        idx_a = content.find("const D=A.data")
        nl    = content.rfind("\n", 0, idx_a)
        if idx_b == -1 or idx_a == -1:
            raise ValueError("Cannot locate const A= block in HTML")
        content = content[:idx_b] + new_block + content[nl:]
    else:
        content = content[:idx_b] + new_block + content[idx_a:]

    # Update visible text counts and date
    content = re.sub(r"\d[\d,]+ licensed sponsors",
                     f"{total_sponsors:,} licensed sponsors", content)
    content = re.sub(r"Updated \d{2} \w+ \d{4}",
                     f"Updated {datetime.now().strftime('%d %b %Y')}", content)

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"HTML updated. Total sponsors: {total_sponsors:,}")


def main():
    print("=" * 50)
    print(f"UK Sponsor Finder Tool Update – {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    csv_url = get_csv_url()

    print("Downloading CSV...")
    r = requests.get(csv_url, timeout=120,
        headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    print(f"Downloaded {len(r.content):,} bytes")

    print("Parsing CSV...")
    rows = list(csv.DictReader(io.StringIO(r.content.decode("latin-1"))))
    print(f"Total rows: {len(rows):,}")

    print("Building data structure...")
    data, totals = build_data_structure(rows)
    total_sponsors = sum(t["total"] for t in totals.values())

    update_html(data, totals, total_sponsors)
    print("Done! GitHub Actions will commit and push the updated index.html")


if __name__ == "__main__":
    main()
