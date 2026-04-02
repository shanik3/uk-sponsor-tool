import requests
import json
import re
import csv
import io
import datetime

GOV_PAGE = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
CSV_FALLBACK = "https://assets.publishing.service.gov.uk/media/register-of-licensed-sponsors-workers.csv"

ROUTES = {
    "Skilled Worker": "SW",
    "Global Business Mobility": "GBM",
    "Creative Worker": "CW",
    "Charity Worker": "CHW",
    "Scale-up": "SU",
}

LONDON_AREAS = {
    "London","Ilford","Harrow","Croydon","Hounslow","Hayes","Wembley",
    "Uxbridge","Barking","DAGENHAM","SUTTON","Richmond","Bromley",
    "Enfield","Romford","Feltham","Twickenham","Wimbledon","Hammersmith",
    "Stanmore","Southall","Ealing","Hackney","Islington","Lewisham",
    "Lambeth","Wandsworth","Greenwich","Bexley","Kingston","Merton",
    "HARROW","ILFORD","WEMBLEY","BARKING"
}
MANCHESTER_AREAS = {
    "Manchester","Bolton","Oldham","Stockport","ROCHDALE","Salford",
    "Altrincham","Bury","Wigan","CHEADLE","Sale","ASHTON-UNDER-LYNE",
    "Rochdale","Cheadle","Ashton-Under-Lyne","Leigh","Heywood","Middleton",
    "Farnworth","Stalybridge","Hyde"
}
WEST_YORKSHIRE_AREAS = {
    "LEEDS","Bradford","Huddersfield","Wakefield","Dewsbury","Halifax",
    "Keighley","Batley","SHIPLEY","Pontefract","Castleford","Wetherby",
    "Leeds","BATLEY","CASTLEFORD","Shipley","Normanton","Cleckheaton",
    "Mirfield","Liversedge","Bingley","Hebden Bridge"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

def get_csv_url():
    try:
        r = requests.get(GOV_PAGE, headers=HEADERS, timeout=15)
        urls = re.findall(r'https://assets\.publishing\.service\.gov\.uk[^"\']*\.csv', r.text)
        if urls:
            return urls[0]
    except Exception as e:
        print(f"Page scrape failed: {e}")
    return CSV_FALLBACK

def get_region(town):
    t = town.strip()
    if t in LONDON_AREAS or t.upper() in {a.upper() for a in LONDON_AREAS}:
        return "London"
    if t in MANCHESTER_AREAS or t.upper() in {a.upper() for a in MANCHESTER_AREAS}:
        return "Manchester"
    if t in WEST_YORKSHIRE_AREAS or t.upper() in {a.upper() for a in WEST_YORKSHIRE_AREAS}:
        return "West Yorkshire"
    return "Other"

def get_route_key(route_name):
    for k, v in ROUTES.items():
        if k in route_name:
            return v
    return "OTH"

def build_data(csv_url):
    print(f"Downloading CSV from: {csv_url}")
    r = requests.get(csv_url, headers=HEADERS, timeout=30)
    r.encoding = "latin-1"
    reader = csv.DictReader(io.StringIO(r.text))

    # out_data[route][region] = {town: {n, c, s:[]}}
    out_data = {}
    out_totals = {}

    for row in reader:
        org = row.get("Organisation Name", "").strip()
        town = row.get("Town/City", "").strip()
        county = row.get("County", "").strip()
        route = row.get("Route", "").strip()
        sector = row.get("Type & Rating", "").strip()

        rkey = get_route_key(route)
        region = get_region(town)
        town_display = town if town else county if county else "Other"

        if rkey not in out_data:
            out_data[rkey] = {}
            out_totals[rkey] = {"total": 0, "regions": {}}
        if region not in out_data[rkey]:
            out_data[rkey][region] = {}
        if town_display not in out_data[rkey][region]:
            out_data[rkey][region][town_display] = {"n": town_display, "c": 0, "s": []}

        out_data[rkey][region][town_display]["c"] += 1
        out_data[rkey][region][town_display]["s"].append([org, county, sector[:2] if sector else "O"])
        out_totals[rkey]["total"] = out_totals[rkey].get("total", 0) + 1
        out_totals[rkey]["regions"][region] = out_totals[rkey]["regions"].get(region, 0) + 1

    # Convert town dicts to sorted lists
    final_data = {}
    for rkey, regions in out_data.items():
        final_data[rkey] = {}
        for region, towns in regions.items():
            sorted_towns = sorted(towns.values(), key=lambda x: x["c"], reverse=True)
            final_data[rkey][region] = sorted_towns

    return final_data, out_totals

def update_html(data, totals):
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()

    new_const = "const A=" + json.dumps({"data": data, "totals": totals}) + ";"

    # Use string split — NOT regex — to avoid corrupting nested JSON
    marker_start = "const A="
    marker_end = ";\nconst D=A.data"

    if marker_start not in html or marker_end not in html:
        print("ERROR: Could not find data markers in index.html")
        return False

    before = html[:html.index(marker_start)]
    after = html[html.index(marker_end):]
    html = before + new_const + after

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Updated index.html at {datetime.datetime.utcnow().isoformat()}")
    return True

if __name__ == "__main__":
    csv_url = get_csv_url()
    data, totals = build_data(csv_url)
    update_html(data, totals)
