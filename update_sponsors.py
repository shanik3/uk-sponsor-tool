import requests
import csv
import json
import re
import io
import os
from datetime import datetime

# ── CONFIG ──────────────────────────────────────────────────────────────────
CSV_URL = "https://assets.publishing.service.gov.uk/media/67f78c5c3ee19a47e7efb5c9/2025-04-10_-_Worker_and_Temporary_Worker.csv"
NETLIFY_HOOK = "https://api.netlify.com/build_hooks/69cd7c140fe066ec3118042e"

# ── ROUTE MAPPING ────────────────────────────────────────────────────────────
ROUTE_MAP = {
    "Skilled Worker": "SW",
    "Global Business Mobility": "GBM",
    "Creative Worker": "CW",
    "Charity Worker": "CHW",
    "Scale-up": "SU",
    "International Sportsperson": "OTH",
    "Seasonal Worker": "OTH",
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
               "Westminster","Lambeth","Wandsworth","Battersea","Brixton",
               "Stratford","Canary Wharf","Poplar","Bow","Stepney","Bethnal Green",
               "Shoreditch","Bermondsey","Peckham","Tooting","Streatham","Norwood",
               "Dulwich","Forest Hill","Catford","Lewisham","Greenwich","Woolwich",
               "Eltham","Sidcup","Orpington","Beckenham","Mitcham","Morden",
               "Wimbledon","New Malden","Surbiton","Teddington","Hampton",
               "Staines","Ashford","Sunbury","Shepperton","Weybridge"],
    "Manchester": ["Manchester","Bolton","Oldham","Stockport","Rochdale","Salford",
                   "Altrincham","Bury","Wigan","Cheadle","Sale","Ashton-Under-Lyne",
                   "Leigh","Heywood","Middleton","Radcliffe","Farnworth","Hyde",
                   "Stalybridge","Stretford","Eccles","Swinton","Irlam"],
    "West Yorkshire": ["Leeds","Bradford","Huddersfield","Wakefield","Dewsbury",
                       "Halifax","Keighley","Batley","Shipley","Pontefract",
                       "Castleford","Wetherby","Normanton","Cleckheaton","Mirfield",
                       "Liversedge","Brighouse","Bingley","Ilkley","Otley"],
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
    i = industry.strip()
    for k, v in SECTOR_MAP.items():
        if k.lower() in i.lower():
            return v
    return "O"

def get_route_key(route):
    if not route:
        return None
    r = route.strip()
    for k, v in ROUTE_MAP.items():
        if k.lower() in r.lower():
            return v
    return None

def download_csv():
    print("Downloading CSV from gov.uk...")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SponsorTool/1.0)"}
    r = requests.get(CSV_URL, headers=headers, timeout=60)
    r.raise_for_status()
    print(f"Downloaded {len(r.content):,} bytes")
    return r.content

def parse_csv(content):
    print("Parsing CSV...")
    # Try different encodings
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
    # Structure: {route_key: {region: {town: [sponsors]}}}
    data = {}
    
    for row in rows:
        # Get column names (flexible)
        org = row.get('Organisation Name', row.get('Organisation name', ''))
        town = row.get('Town/City', row.get('Town', ''))
        county = row.get('County', '')
        route = row.get('Route', '')
        industry = row.get('Industry', row.get('Type & Rating', ''))
        
        if not org:
            continue
        
        rk = get_route_key(route)
        if not rk:
            rk = "OTH"
        
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
    """Convert to the format expected by the HTML"""
    result = {}
    totals = {}
    
    for rk, regions in data.items():
        result[rk] = {}
        totals[rk] = {"total": 0, "regions": {}}
        
        for region, towns in regions.items():
            town_list = []
            region_count = 0
            
            # Sort towns by count descending
            sorted_towns = sorted(towns.items(), key=lambda x: len(x[1]), reverse=True)
            
            for town, sponsors in sorted_towns:
                if len(sponsors) == 0:
                    continue
                # Sort sponsors alphabetically, keep top 300 for display
                sorted_sponsors = sorted(sponsors, key=lambda x: x[0])
                town_list.append({
                    "n": town,
                    "c": len(sponsors),
                    "s": sorted_sponsors[:300]  # display cap
                })
                region_count += len(sponsors)
            
            if town_list:
                result[rk][region] = town_list
                totals[rk]["regions"][region] = region_count
                totals[rk]["total"] += region_count
    
    return result, totals

def update_html(formatted_data, formatted_totals):
    print("Updating HTML file...")
    
    # Read current index.html
    if not os.path.exists("index.html"):
        print("ERROR: index.html not found!")
        return False
    
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    
    # Build new data JSON
    new_data_json = json.dumps({"data": formatted_data}, separators=(',', ':'))
    new_totals_json = json.dumps(formatted_totals, separators=(',', ':'))
    
    # Replace the data constant (A={"data":...})
    # Find and replace the A= assignment
    pattern = r'const A=\{["\']data["\']\s*:'
    if re.search(pattern, html):
        # Find the full A={...} block
        start = html.find('const A=')
        if start == -1:
            print("Could not find const A= in HTML")
            return False
        
        # Find matching brace
        depth = 0
        i = start + len('const A=')
        while i < len(html):
            if html[i] == '{':
                depth += 1
            elif html[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
            i += 1
        
        old_block = html[start:end]
        new_block = f'const A={new_data_json}'
        html = html[:start] + new_block + html[end:]
        print("Data block updated successfully")
    else:
        print("WARNING: Could not find data pattern, skipping data update")
    
    # Replace totals (TT=...)
    tt_pattern = r'const TT=A\.totals;'
    if re.search(tt_pattern, html):
        # Totals are derived from A.totals in original - add them separately
        pass  # Keep as is if totals come from A.totals
    
    # Update the subtitle with new count
    total_sponsors = sum(v["total"] for v in formatted_totals.values())
    subtitle_pattern = r'(\d[\d,]*) licensed sponsors'
    html = re.sub(subtitle_pattern, f'{total_sponsors:,} licensed sponsors', html)
    
    # Update "Updated daily" footer with actual date
    today = datetime.now().strftime("%d %b %Y")
    html = re.sub(r'Updated daily', f'Updated {today}', html)
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"HTML updated. Total sponsors: {total_sponsors:,}")
    return True

def trigger_netlify():
    print("Triggering Netlify rebuild...")
    try:
        r = requests.post(NETLIFY_HOOK, json={}, timeout=15)
        if r.status_code == 200:
            print("Netlify rebuild triggered successfully!")
        else:
            print(f"Netlify hook returned status: {r.status_code}")
    except Exception as e:
        print(f"Failed to trigger Netlify: {e}")

def main():
    print(f"\n{'='*50}")
    print(f"UK Sponsor Tool Update — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")
    
    try:
        content = download_csv()
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
