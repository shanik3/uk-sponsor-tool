#!/usr/bin/env python3
"""
UK Sponsor Finder Tool - Daily Auto-Update Script
GitHub repo: shanik3/uk-sponsor-tool
Netlify site: uk-sponser-finder-tool.netlify.app
"""

import json
import csv
import io
import requests
from datetime import datetime
from collections import defaultdict
from bs4 import BeautifulSoup

NETLIFY_HOOK = "https://api.netlify.com/build_hooks/69cd7c140fe066ec3118042e"
GOV_PAGE     = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
HTML_FILE    = "index.html"

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
    r = requests.get(GOV_PAGE, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "Worker and Temporary Worker" in href and href.endswith(".csv"):
            url = href if href.startswith("http") else "https://assets.publishing.service.gov.uk" + href
            print(f"Found CSV URL: {url}")
            return url
    raise ValueError("Could not find CSV URL on gov.uk page")


def classify_region(town, county):
    t = (town or "").strip().title()
    c = (county or "").strip().title()
    if any(x in t or x in c for x in ["London", "Greater London", "Middlesex"]):
        return "London"
    if t in LONDON_BOROUGHS or c in LONDON_BOROUGHS:
        return "London"
    if any(x in t or x in c for x in ["Manchester", "Lancashire", "Salford"]):
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
        route_raw = (row.get("Route") or "").strip().lower()
        sub_tier  = (row.get("Sub Tier") or "").strip()

        rl = route_raw
        if "skilled worker" in rl:
            rk = "SW"
        elif "global business mobility" in rl or "gbm" in rl:
            rk = "GBM"
        elif "creative worker" in rl:
            rk = "CW"
        elif "charity worker" in rl or "religious worker" in rl:
            rk = "CHW"
        elif "scale-up" in rl or "scale up" in rl:
            rk = "SU"
        else:
            rk = "OTH"

        region   = classify_region(town, county)
        town_key = town.upper() if town else "UNKNOWN"
        code     = sub_tier[:2].upper() if sub_tier else "O"

        raw[rk][region][town_key]["c"] += 1
        raw[rk][region][town_key]["s"].append([org, county, code])

    out_data   = {}
    out_totals = {}

    for rk in ROUTES:
        out_data[rk] = {}
        route_total  = 0
        region_totals = {"London": 0, "Manchester": 0, "West Yorkshire": 0, "Other": 0}

        for region in ["London", "Manchester", "West Yorkshire", "Other"]:
            towns = raw[rk].get(region, {})
            town_list = sorted(
                [{"n": tn, "c": info["c"], "s": info["s"]} for tn, info in towns.items()],
                key=lambda x: x["c"], reverse=True
            )
            out_data[rk][region] = town_list
            region_count = sum(t["c"] for t in town_list)
            region_totals[region] = region_count
            route_total += region_count

        out_totals[rk] = {"total": route_total, "regions": region_totals}

    return out_data, out_totals


def update_html(data, totals, total_sponsors):
    print("Updating HTML file...")
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    # ── SAFE REPLACEMENT using string split, NOT regex ──────────────────────
    # The JS has exactly:   const A={...huge JSON...};
    # followed on the next line by:   const D=A.data,TT=A.totals;
    #
    # Strategy: find "const A=" then find the matching closing by scanning forward
    # to the next occurrence of "\nconst " after the opening brace.
    # Even safer: split on the known marker that comes RIGHT AFTER const A=...;
    MARKER_BEFORE = "const A="
    MARKER_AFTER  = ";\nconst D=A.data"   # the exact line that follows in the original

    # Build replacement
    A_obj = {"data": data, "totals": totals}
    new_json = json.dumps(A_obj, ensure_ascii=False, separators=(",", ":"))
    new_block = f"const A={new_json}"

    idx_before = content.find(MARKER_BEFORE)
    idx_after  = content.find(MARKER_AFTER)

    if idx_before == -1 or idx_after == -1:
        print("WARNING: Could not find exact markers. Trying fallback...")
        # Fallback: find const A= ... const D=
        FALLBACK_AFTER = "const D=A.data"
        idx_before = content.find("const A=")
        idx_after  = content.find(FALLBACK_AFTER)
        if idx_before == -1 or idx_after == -1:
            raise ValueError("Could not locate const A= block in HTML. Aborting.")
        # idx_after points to "const D=" — go back to find the ; before it
        # Walk backwards from idx_after to find \n
        nl = content.rfind("\n", 0, idx_after)
        content = content[:idx_before] + new_block + content[nl:]
    else:
        # Replace from "const A=" up to (but not including) ";\nconst D=A.data"
        content = content[:idx_before] + new_block + content[idx_after:]

    # Update the visible sponsor count text in the page
    import re
    date_str = datetime.now().strftime("%d %b %Y")
    content = re.sub(r"\d[\d,]+ licensed sponsors", f"{total_sponsors:,} licensed sponsors", content)
    content = re.sub(r"Updated \d{2} \w+ \d{4}", f"Updated {datetime.now().strftime('%d %b %Y')}", content)

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"HTML updated. Total sponsors: {total_sponsors:,}")


def trigger_netlify():
    print("Triggering Netlify rebuild...")
    r = requests.post(NETLIFY_HOOK, timeout=30)
    print(f"Netlify status: {r.status_code}")


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print("=" * 50)
    print(f"UK Sponsor Finder Tool Update – {now}")
    print("=" * 50)

    csv_url = get_csv_url()

    print("Downloading CSV...")
    r = requests.get(csv_url, timeout=120)
    print(f"Downloaded {len(r.content):,} bytes")

    print("Parsing CSV...")
    text = r.content.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    print(f"Total rows: {len(rows):,}")

    print("Building data structure...")
    data, totals = build_data_structure(rows)

    total_sponsors = sum(t["total"] for t in totals.values())
    update_html(data, totals, total_sponsors)
    trigger_netlify()


if __name__ == "__main__":
    main()
