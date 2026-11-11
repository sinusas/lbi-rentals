#!/usr/bin/env python3
"""Collect every easily scrapeable south-LBI rental that fits the trip and write all/houses.json
for the /all/ page.

Sources:
  - lbi.vacations: every listing (one page). No availability (its calendars never show bookings).
  - Van Dyk Group (realtimerental.com): search for Aug 7-14, 2027, so every result was open that day.
    Rates come from each house's p.asp page (the rate period covering Aug 7, 2027).
Coordinates come from the US Census geocoder, with OpenStreetMap Nominatim as a fallback.

Run:  python3 build_all.py          (raw pages are cached in .cache/; --fresh refetches them)
"""
import hashlib, html, json, pathlib, re, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).parent
CACHE = ROOT / ".cache"; CACHE.mkdir(exist_ok=True)
OUT = ROOT / "all" / "houses.json"
FRESH = "--fresh" in sys.argv
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) lbi-rentals-map/1.0"}

MIN_SLEEPS = 8
# South end of the island: Holgate up through Brant Beach (Ship Bottom starts ~39.637)
LAT_MAX, LAT_MIN, LNG_MIN = 39.636, 39.48, -74.27

VANDYK_POID = "1499B1537o0OL"
RTR = "https://www.realtimerental.com"


def fetch(url, data=None, key=None, ttl_fresh=True):
    key = key or hashlib.sha1((url + (data or "")).encode()).hexdigest()
    f = CACHE / key
    if f.exists() and not (FRESH and ttl_fresh):
        return f.read_text(errors="replace")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data.encode() if data else None, headers=UA)
            with urllib.request.urlopen(req, timeout=40) as r:
                s = r.read().decode("utf-8", "replace")
            f.write_text(s)
            return s
        except Exception as e:
            print("  retry", url, e, file=sys.stderr)
            time.sleep(3)
    return ""


def text(s):
    s = re.sub(r"<(script|style).*?</\1>", " ", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return html.unescape(re.sub(r"\s+", " ", s)).strip()


def num(x):
    try:
        return float(x) if "." in x else int(x)
    except Exception:
        return None


# ── lbi.vacations ────────────────────────────────────────────────────────────
def lbi_vacations():
    s = fetch("https://lbi.vacations/properties", key="lbiv-index")
    out = []
    for m in re.finditer(r'<article class="cl-stay-card" data-slug="([^"]*)"(.*?)</article>', s, re.S):
        b = m.group(2)
        g = lambda p: (re.search(p, b, re.S) or [None, None])[1]
        price = g(r'__price">\s*\$([\d,]+)')
        out.append({
            "src": "lbi.vacations",
            "url": g(r'href="([^"]+)"'),
            "title": html.unescape(g(r'__title">([^<]*)') or "").strip(),
            "addr_raw": html.unescape(g(r'__address">([^<]*)') or "").strip(),
            "kind": g(r'__badge">([^<]*)'),
            "price": int(price.replace(",", "")) if price else None,
            "bedrooms": num(g(r"([\d.]+) Beds") or ""),
            "baths": num(g(r"([\d.]+) Baths") or ""),
            "sleeps": num(g(r"([\d.]+) Guests") or ""),
            "photo": g(r'<img src="([^"]+)"'),
            "available": None,
        })
    out = [h for h in out if (h["sleeps"] or 0) >= MIN_SLEEPS]

    def detail(h):
        t = text(fetch(h["url"]))
        t = re.sub(r"Pool, hot tub, and outdoor amenities: use at your own risk\.?", "", t)   # house-rules boilerplate
        h["pool"] = bool(re.search(r"\bpools?\b(?! table)", t, re.I)) and not re.search(r"\bno (private )?pool\b", t, re.I)
        d = re.search(r"About this home\s*(.{40,}?)\s*Read more", t)
        h["desc"] = d and d[1].strip()[:700]
        return h
    with ThreadPoolExecutor(6) as ex:
        out = list(ex.map(detail, out))
    print(f"lbi.vacations: {len(out)} listings sleeping {MIN_SLEEPS}+", file=sys.stderr)
    return out


# ── Van Dyk via realtimerental ───────────────────────────────────────────────
def vandyk_search(sleeps):
    form = {
        "poid": VANDYK_POID, "AS": "F", "geo_code": "Long Beach Island, NJ", "GeographyID": "1323",
        "OfficeID": "1537", "lhost_name": "Van Dyk Group", "PT": "B", "RateTypeID": "ALL",
        "total_sleeps": str(sleeps), "Bed_Rooms": "", "baths": "",
        "month": "8", "day": "7", "year": "2027", "emonth": "8", "eday": "14", "eyear": "2027",
        "start_date": "8/7/2027", "end_date": "8/14/2027", "list_PagingShowAll": "ALL", "Query1": "Find Property",
    }
    s = fetch(f"{RTR}/rrv10/visitor/search.asp", urllib.parse.urlencode(form), key=f"vandyk-s{sleeps}")
    if "8/7/2027 to 8/14/2027" not in s:
        print(f"  Van Dyk search for sleeps={sleeps} did not run for Aug 7-14", file=sys.stderr)
        return []
    out = []
    for chunk in s.split("Property_Information_Under_Picture")[1:]:
        t = text(chunk[:8000])
        pid = re.search(r"Property ID:\s*(\d+)", t)
        addr = re.search(r"gmapwin\('([^']*)'\)", chunk)
        if not pid or not addr:
            continue
        g = lambda p: (re.search(p, t) or [None, None])[1]
        full, half = num(g(r"Full Bath\(s\):\s*(\d+)") or "0") or 0, num(g(r"Half Bath\(s\):\s*(\d+)") or "0") or 0
        a = [x.strip() for x in html.unescape(addr[1]).split(",") if x.strip()]
        out.append({
            "src": "Van Dyk", "pid": pid[1],
            "url": f"{RTR}/p.asp?mp={VANDYK_POID}~{pid[1]}",
            "addr_raw": re.sub(r"\s*-\s*ALARM.*", "", a[0]) + (", " + a[1] if len(a) > 1 else ""),
            "area": a[1] if len(a) > 1 else None,
            "kind": g(r"Property ID:\s*\d+\s+(.*?)\s+Sleeps"),
            "sleeps": num(g(r"Sleeps:\s*(\d+)") or ""),
            "bedrooms": num(g(r"Bedroom\(s\):\s*(\d+)") or ""),
            "baths": full + half / 2 if full else None,
            "photo": (lambda p: p and RTR + p[1])(re.search(r'src="(/rrv10/RentalPhotos/[^"]+)"', s[:s.find(chunk)][-3000:])),
            "available": True,
        })
    return out


def vandyk():
    seen, out = set(), []
    for sl in range(MIN_SLEEPS, 16):
        for h in vandyk_search(sl):
            if h["pid"] not in seen:
                seen.add(h["pid"]); out.append(h)

    def detail(h):
        s = fetch(h["url"])
        t = text(s)
        rates = re.findall(r"\$\s*([\d,]+(?:\.\d\d)?)\s+(\w{3}) (\d+), (\d{4}) - (\w{3}) (\d+), (\d{4})", t)
        h["price"] = None
        for amt, m1, d1, y1, m2, d2, y2 in rates:
            a = time.strptime(f"{m1} {d1} {y1}", "%b %d %Y"); b = time.strptime(f"{m2} {d2} {y2}", "%b %d %Y")
            if a <= time.strptime("Aug 7 2027", "%b %d %Y") <= b:
                h["price"] = int(float(amt.replace(",", "")))
        h["pool"] = bool(re.search(r"Private Pool|Outdoor Pool|Community Pool|Heated Pool", t))
        d = re.search(r"Description:\s*(.{20,600}?)(?:Electronics Description|Request Information)", t)
        h["desc"] = d and d[1].strip()
        h["title"] = re.search(r"Listing Information for (.*?) ID:", t) and re.search(r"Listing Information for (.*?) ID:", t)[1]
        return h
    with ThreadPoolExecutor(6) as ex:
        out = list(ex.map(detail, out))
    print(f"Van Dyk: {len(out)} houses open Aug 7-14 sleeping {MIN_SLEEPS}+", file=sys.stderr)
    return out


# ── geocoding ────────────────────────────────────────────────────────────────
GEO_CACHE = CACHE / "geocode.json"
geo = json.loads(GEO_CACHE.read_text()) if GEO_CACHE.exists() else {}

STREET_FIX = [(r"\bEighth\b", "8th"), (r"\bSeventh\b", "7th"), (r"\bSixth\b", "6th"), (r"\bFifth\b", "5th"),
              (r"\bFourth\b", "4th"), (r"\bThird\b", "3rd"), (r"\bSecond\b", "2nd"), (r"\bFirst\b", "1st"),
              (r"\bNinth\b", "9th"), (r"\bTenth\b", "10th")]


def clean_street(raw):
    s = raw.split(",")[0]
    s = re.sub(r"(?i)\b(beach haven( park| gardens| crest| terrace)?|holgate|brant beach|nj|new jersey|usa)\b.*", "", s).strip(" .,-")
    s = re.sub(r"\s+\d{5}$", "", s)                         # trailing zip (house numbers can be 5 digits too)
    s = re.sub(r"(?i)#\s*\w+|\bunit\b.*|\bapt\b.*|\s*-\s*\d+ bedroom.*|\(.*?\)|\(.*", "", s).strip()
    s = re.sub(r"(?<=\d)(?!(?:st|nd|rd|th)\b)(?=[A-Za-z]{2,})", " ", s)           # 102WRooseveltAve -> 102 WRooseveltAve
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)                # WRooseveltAve -> W Roosevelt Ave
    s = re.sub(r"\b([NSEW])(?=[A-Z][a-z])", r"\1 ", s)
    for a, b in STREET_FIX:
        s = re.sub(a, b, s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


# Villages from south to north with their latitude bands (from Van Dyk-labeled houses and OSM)
VILLAGES = [
    ("Holgate", 39.50, 39.5495, "Long Beach Township"),
    ("North Beach Haven", 39.569, 39.5785, "Long Beach Township"),   # before "Beach Haven" so it matches first
    ("Beach Haven Gardens", 39.577, 39.5855, "Long Beach Township"),
    ("Beach Haven Terrace", 39.582, 39.5905, "Long Beach Township"),
    ("Beach Haven Park", 39.596, 39.6035, "Long Beach Township"),
    ("Beach Haven Crest", 39.608, 39.618, "Long Beach Township"),
    ("Beach Haven West", 0, 0, None),                                 # mainland
    ("Beach Haven", 39.545, 39.5725, "Beach Haven"),
    ("Spray Beach", 39.575, 39.581, "Long Beach Township"),
    ("The Dunes", 39.586, 39.5945, "Long Beach Township"),
    ("Haven Beach", 39.589, 39.5985, "Long Beach Township"),
    ("Peahala Park", 39.600, 39.607, "Long Beach Township"),
    ("Brighton Beach", 39.604, 39.6115, "Long Beach Township"),
    ("Brant Beach", 39.612, 39.638, "Long Beach Township"),
    ("Ship Bottom", 39.636, 39.656, "Ship Bottom"),
    ("Surf City", 39.65, 39.672, "Surf City"),
    ("Harvey Cedars", 39.67, 39.71, "Harvey Cedars"),
    ("North Beach", 39.69, 39.72, "Long Beach Township"),
    ("Loveladies", 39.71, 39.74, "Long Beach Township"),
    ("High Bar Harbor", 39.73, 39.75, "Long Beach Township"),
    ("Barnegat Light", 39.74, 39.77, "Barnegat Light"),
]


def village_in(*texts):
    t = " ".join(x for x in texts if x)
    for v in VILLAGES:
        if re.search(r"(?i)\b" + re.escape(v[0]) + r"\b", t):
            return v
    return None


def _census(street):
    q = urllib.parse.urlencode({"address": f"{street}, Long Beach Township, NJ 08008", "benchmark": "Public_AR_Current", "format": "json"})
    try:
        d = json.loads(fetch(f"https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?{q}", key="census-" + hashlib.sha1(q.encode()).hexdigest(), ttl_fresh=False))
        return [{"lat": m["coordinates"]["y"], "lng": m["coordinates"]["x"], "how": "census", "match": m["matchedAddress"]} for m in d["result"]["addressMatches"]]
    except Exception:
        return []


def _osm(street, town):
    q = urllib.parse.urlencode({"q": f"{street}, {town}, NJ", "format": "json", "limit": 5, "countrycodes": "us"})
    key = "nom-" + hashlib.sha1(q.encode()).hexdigest()
    if not (CACHE / key).exists():
        time.sleep(1.1)   # Nominatim usage policy: 1 request per second
    try:
        d = json.loads(fetch(f"https://nominatim.openstreetmap.org/search?{q}", key=key, ttl_fresh=False) or "[]")
    except Exception:
        d = []
    return [{"lat": float(r["lat"]), "lng": float(r["lon"]), "how": "osm", "match": r["display_name"][:90],
             "exact": r.get("addresstype") in ("building", "place", "house") or r["display_name"].split(",")[0].strip() == street.split()[0]}
            for r in d]


def geocode(street, village=None):
    """Return {lat, lng, how, match, approx}. Census only matches on the island-wide 08008 ZIP, so duplicate street
    names (numbered streets, Virginia Ave...) can land in the wrong town: cross-check with OpenStreetMap and, when the
    listing names its village, keep the candidate inside that village."""
    ck = f"{street}|{village and village[0]}"
    if ck in geo:
        return geo[ck]
    towns = [village[3]] if village and village[3] else ["Long Beach Township", "Beach Haven"]
    cands = _census(street) + [c for t in towns for c in _osm(street, t)]
    if village and village[3]:
        lo, hi = village[1] - .002, village[2] + .002
        inside = [c for c in cands if lo <= c["lat"] <= hi]
        res = (sorted(inside, key=lambda c: (c["how"] != "census", not c.get("exact")))[:1] or [None])[0]
        if res:
            res = dict(res, approx=not (res["how"] == "census" or res.get("exact")))
        elif cands:   # nothing inside the named village (listing may name the wrong one): best guess, flagged
            res = dict(cands[0], approx=True)
    else:
        census = [c for c in cands if c["how"] == "census"]
        osm = [c for c in cands if c["how"] == "osm"]
        res = census[0] if census else (osm[0] if osm else None)
        if res:
            agree = any(abs(o["lat"] - res["lat"]) < .003 for o in osm) if res["how"] == "census" else res.get("exact")
            res = dict(res, approx=not agree)
    geo[ck] = res
    GEO_CACHE.write_text(json.dumps(geo, indent=1))
    return res


def key_of(street):
    s = street.lower()
    s = re.sub(r"\b(street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|court|ct|drive|dr)\b\.?", "", s)
    s = re.sub(r"\b(east|e|west|w|north|n|south|s)\b\.?", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def area_of(lat):
    """Coarse area for filtering, from latitude."""
    if lat < 39.548: return "Holgate"
    if lat < 39.5715: return "Beach Haven"
    if lat < 39.586: return "North Beach Haven–BH Terrace"
    if lat < 39.6035: return "The Dunes–BH Park"
    if lat < 39.618: return "Peahala Park–BH Crest"
    return "Brant Beach"


def main():
    houses = lbi_vacations() + vandyk()
    # Houses already on the main page or /ai/ (match by street address)
    known = {}
    for page, label in ((ROOT / "index.html", "main"), (ROOT / "ai" / "index.html", "ai")):
        for m in re.finditer(r'id: "([^"]+)", option: "([A-Z])", addr: "([^"]+)"', page.read_text()):
            known.setdefault(key_of(m[3]), {})[label] = m[2]

    kept, dropped = [], []
    for h in houses:
        street = clean_street(h["addr_raw"] or h.get("title") or "")
        if not re.match(r"\d", street):
            street = clean_street(h.get("title") or "")
        h["addr"] = street
        v = village_in(h.get("area"), h["addr_raw"], h.get("title"))
        if v and (not v[3] or v[1] > LAT_MAX):
            continue   # mainland, or a village north of the area
        g = geocode(street, v) if re.match(r"\d", street) else None
        if not g:
            dropped.append(("no geocode", street, h["url"])); continue
        if not (LAT_MIN < g["lat"] < LAT_MAX and g["lng"] > LNG_MIN):
            continue
        h.update(lat=round(g["lat"], 6), lng=round(g["lng"], 6), geo=g["how"], approx=g.get("approx"), area=area_of(g["lat"]),
                 village=v and v[0])
        h["on"] = known.get(key_of(street))
        kept.append(h)

    # Same house listed by both sources: merge into one entry with both links
    merged = {}
    for h in kept:
        k = key_of(h["addr"])
        if k in merged and abs(merged[k]["lat"] - h["lat"]) > .0025:
            k += f"@{h['lat']:.3f}"
        if k in merged:
            a = merged[k]
            a.setdefault("also", []).append({"src": h["src"], "url": h["url"], "price": h.get("price")})
            if h["available"]: a["available"] = True
            if not a.get("price") and h.get("price"): a["price"] = h["price"]
            a["pool"] = a.get("pool") or h.get("pool")
        else:
            merged[k] = h
    out = []
    for h in merged.values():
        out.append({k: h.get(k) for k in ("addr", "area", "lat", "lng", "src", "url", "also", "kind", "price", "bedrooms",
                                           "baths", "sleeps", "pool", "available", "photo", "desc", "on", "geo", "approx", "village")})
    out.sort(key=lambda h: (h["price"] is None, h["price"] or 0))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"updated": time.strftime("%Y-%m-%d"), "houses": out}, indent=0, ensure_ascii=False))
    print(f"wrote {len(out)} houses to {OUT}", file=sys.stderr)
    for d in dropped:
        print("  dropped:", *d, file=sys.stderr)


if __name__ == "__main__":
    main()
