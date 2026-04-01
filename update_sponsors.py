import requests
import csv
import json
import re
import io
import os
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────────────
GOV_PAGE = "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"
NETLIFY_HOOK = "https://api.netlify.com/build_hooks/69cd7c140fe066ec3118042e"

ROUTE_MAP = {
    "Skilled Worker": "SW",
    "Global Business Mobility": "GBM",
    "Creative Worker": "CW",
    "Charity Worker": "CHW",
    "Scale-up": "SU",
    "Senior or Specialist Worker": "GBM",
    "Graduate Trainee": "GBM",
    "UK Expansion Worker": "GBM",
    "Service Supplier": "GBM",
    "Secondment Worker": "GBM",
    "Intra-Company Routes": "GBM",
}

SECTOR_MAP = {
    "Health & Care": "H",
    "Social Care": "SC",
    "Education": "E",
    "IT & Telecoms": "T",
    "Hospitality & Catering": "F",
    "Retail": "R",
    "Construction & Infrastructure": "C",
    "Transport & Logistics": "TR",
    "Finance": "FL",
    "Legal": "FL",
    "Engineering": "EN",
}

REGIONS = {
    "London": ["London","Ilford","Harrow","Croydon","Hounslow","Hayes","Wembley",
               "Uxbridge","Barking","Dagenham","Sutton","Richmond","Hammersmith",
               "Twickenham","Bromley","Feltham","Stanmore","Wimbledon","Enfield",
               "Barnet","Edgware","Greenford","Southall","Ealing","Brentford",
               "Kingston","Romford","Lewisham","Hackney","Islington","Camden",
               "Westminster","Lambeth","Wandsworth","Stratford","Bow","Shoreditch"],
    "Manchester": ["Manchester","Bolton","Oldham","Stockport","Rochdale","Salford",
                   "Altrincham","Bury","Wigan","Cheadle","Sale","Ashton-Under-Lyne",
                   "Leigh","Heywood","Middleton","Farnworth","Hyde","Stalybridge"],
    "West Yorkshire": ["Leeds","Bradford","Huddersfield","Wakefield","Dewsbury",
                       "Halifax","Keighley","Batley","Shipley","Pontefract",
                       "Castleford","Wetherby","Normanton","Cleckheaton","Mirfield"],
}

def get_region(town):
    t = town.strip().upper()
    for region, towns in REGIONS.items():
        for rt in towns:
            if rt.upper() in t or t in rt.upper():
                return region
    return "Other"

def get_sector(industry):
    if not industry:
        return "O"
    for k, v in SECTOR_MAP.items():
        if k.lower() in industry.lower():
            return v
    return "O"

def get_route_key(route):
    if not route:
        return "OTH"
    for k, v in ROUTE_MAP.items():
        if k.lower() in route.lower():
            return v
    return "OTH"

def find_csv_url():
    """Scrape the gov.uk page to find the latest CSV download URL automatically."""
    print("Finding latest CSV URL from gov.uk...")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SponsorTool/1.0)"}
    r = requests.get(GOV_PAGE, headers=headers, timeout=30)
    r.raise_for_status()
    
    # Look for Worker and Temporary Worker CSV links
    patterns = [
        r'href="(https://assets\.publishing\.service\.gov\.uk[^"]*Worker[^"]*\.csv)"',
        r'href="(https://assets\.publishing\.service\.gov\.uk[^"]*worker[^"]*\.csv)"',
        r'href="(/media/[^"]*Worker[^"]*\.csv)"',
        r'href="(/media/[^"]*worker[^"]*\.csv)"',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, r.text, re.IGNORECASE)
        if matches:
            url = matches[0]
            if url.startswith('/'):
                url = 'https://assets.publishing.service.gov.uk' + url
            print(f"Found CSV URL: {url}")
            return url
    
    raise Exception("Could not find CSV URL on gov.uk page")

def download_csv(url):
    print(f"Downloading CSV...")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SponsorTool/1.0)"}
    r = requests.get(url, headers=headers, timeout=120)
    r.raise_for_status()
    print(f"Downloaded {len(r.content):,} bytes")
    return r.content

def parse_csv(content):
    print("Parsing CSV...")
    for enc in ['latin-1', 'utf-8', 'cp1252']:
        try:
            text = content.decode(enc)
            break
        except:
            continue
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    print(f"Total rows: {len(rows):,}")
    return rows

def build_data(rows):
    print("Building data structure...")
    data = {}
    for row in rows:
        org = row.get('Organisation Name', row.get('Organisation name', ''))
        town = row.get('Town/City', row.get('Town', ''))
        county = row.get('County', '')
        route = row.get('Route', '')
        industry = row.get('Industry', row.get('Type & Rating', ''))
        if not org:
            continue
        rk = get_route_key(route)
        region = get_region(town)
        t = town.strip().title() if town else "Unknown"
        sec = get_sector(industry)
        if rk not in data:
            data[rk] = {}
        if region not in data[rk]:
            data[rk][region] = {}
        if t not in data[rk][region]:
            data[rk][region][t] = []
        data[rk][region][t].append([org.strip(), county.strip() if county else "", sec])
    return data

def format_for_html(data):
    result = {}
    totals = {}
    for rk, regions in data.items():
        result[rk] = {}
        totals[rk] = {"total": 0, "regions": {}}
        for region, towns in regions.items():
            town_list = []
            region_count = 0
            for town, sponsors in sorted(towns.items(), key=lambda x: len(x[1]), reverse=True):
                if not sponsors:
                    continue
                town_list.append({
                    "n": town,
                    "c": len(sponsors),
                    "s": sorted(sponsors, key=lambda x: x[0])[:300]
                })
                region_count += len(sponsors)
            if town_list:
                result[rk][region] = town_list
                totals[rk]["regions"][region] = region_count
                totals[rk]["total"] += region_count
    return result, totals

def update_html(formatted_data, formatted_totals):
    print("Updating HTML file...")
    if not os.path.exists("index.html"):
        print("ERROR: index.html not found!")
        return False
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    new_json = json.dumps({"data": formatted_data}, separators=(',', ':'))
    
    start = html.find('const A=')
    if start == -1:
        print("Could not find const A= in HTML")
        return False
    depth = 0
    i = start + len('const A=')
    end = i
    while i < len(html):
        if html[i] == '{':
            depth += 1
        elif html[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    
    html = html[:start] + f'const A={new_json}' + html[end:]
    
    total = sum(v["total"] for v in formatted_totals.values())
    html = re.sub(r'[\d,]+ licensed sponsors', f'{total:,} licensed sponsors', html)
    
    today = datetime.now().strftime("%d %b %Y")
    html = re.sub(r'Updated[\s\w]+\d{4}|Updated daily', f'Updated {today}', html)
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML updated. Total sponsors: {total:,}")
    return True

def trigger_netlify():
    print("Triggering Netlify rebuild...")
    try:
        r = requests.post(NETLIFY_HOOK, json={}, timeout=15)
        print(f"Netlify status: {r.status_code}")
    except Exception as e:
        print(f"Netlify trigger failed: {e}")

def main():
    print(f"\n{'='*50}")
    print(f"UK Sponsor Tool Update — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")
    try:
        url = find_csv_url()
        content = download_csv(url)
        rows = parse_csv(content)
        data = build_data(rows)
        formatted_data, formatted_totals = format_for_html(data)
        success = update_html(formatted_data, formatted_totals)
        if success:
            trigger_netlify()
            print("\n✅ Update complete!")
        else:
            print("\n❌ HTML update failed")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
