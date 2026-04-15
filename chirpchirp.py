#!/usr/bin/env python3
"""ChirpChirp: query Repeaterbook by zip + radius, write a Chirp CSV."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

import requests

RB_NA_URL = "https://www.repeaterbook.com/api/export.php"
RB_ROW_URL = "https://www.repeaterbook.com/api/exportROW.php"
ZIPPO_URL = "https://api.zippopotam.us/{country}/{postal}"

BANDS = {
    "2m":    (144.0, 148.0),
    "1.25m": (222.0, 225.0),
    "70cm":  (420.0, 450.0),
    "33cm":  (902.0, 928.0),
}

STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}

STATE_BBOX = {
    "AL": (30.22, 35.01, -88.47, -84.89), "AK": (51.21, 71.44, -179.15, -129.98),
    "AZ": (31.33, 37.00, -114.82, -109.04), "AR": (33.00, 36.50, -94.62, -89.64),
    "CA": (32.53, 42.01, -124.48, -114.13), "CO": (36.99, 41.00, -109.06, -102.04),
    "CT": (40.98, 42.05, -73.73, -71.79),   "DE": (38.45, 39.84, -75.79, -75.04),
    "DC": (38.79, 38.99, -77.12, -76.91),   "FL": (24.52, 31.00, -87.63, -80.03),
    "GA": (30.36, 35.00, -85.61, -80.84),   "HI": (18.91, 22.24, -160.25, -154.75),
    "ID": (42.00, 49.00, -117.24, -111.04), "IL": (36.97, 42.51, -91.51, -87.02),
    "IN": (37.77, 41.76, -88.10, -84.78),   "IA": (40.38, 43.50, -96.64, -90.14),
    "KS": (36.99, 40.00, -102.05, -94.59),  "KY": (36.50, 39.15, -89.57, -81.96),
    "LA": (28.93, 33.02, -94.04, -88.82),   "ME": (43.06, 47.46, -71.08, -66.95),
    "MD": (37.89, 39.72, -79.49, -75.05),   "MA": (41.24, 42.89, -73.51, -69.93),
    "MI": (41.70, 48.31, -90.42, -82.41),   "MN": (43.50, 49.38, -97.24, -89.49),
    "MS": (30.17, 34.99, -91.66, -88.10),   "MO": (35.99, 40.61, -95.77, -89.10),
    "MT": (44.36, 49.00, -116.05, -104.04), "NE": (40.00, 43.00, -104.05, -95.31),
    "NV": (35.00, 42.00, -120.01, -114.04), "NH": (42.70, 45.31, -72.56, -70.61),
    "NJ": (38.93, 41.36, -75.56, -73.89),   "NM": (31.33, 37.00, -109.05, -103.00),
    "NY": (40.50, 45.02, -79.76, -71.86),   "NC": (33.84, 36.59, -84.32, -75.46),
    "ND": (45.94, 49.00, -104.05, -96.55),  "OH": (38.40, 41.98, -84.82, -80.52),
    "OK": (33.62, 37.00, -103.00, -94.43),  "OR": (41.99, 46.29, -124.57, -116.46),
    "PA": (39.72, 42.27, -80.52, -74.69),   "RI": (41.15, 42.02, -71.86, -71.12),
    "SC": (32.03, 35.22, -83.35, -78.54),   "SD": (42.48, 45.94, -104.06, -96.44),
    "TN": (34.98, 36.68, -90.31, -81.65),   "TX": (25.84, 36.50, -106.65, -93.51),
    "UT": (37.00, 42.00, -114.05, -109.04), "VT": (42.73, 45.02, -73.44, -71.46),
    "VA": (36.54, 39.47, -83.68, -75.24),   "WA": (45.54, 49.00, -124.73, -116.92),
    "WV": (37.20, 40.64, -82.64, -77.72),   "WI": (42.49, 47.08, -92.89, -86.25),
    "WY": (40.99, 45.01, -111.06, -104.05),
}

CHIRP_HEADER = [
    "Location", "Name", "Frequency", "Duplex", "Offset", "Tone",
    "rToneFreq", "cToneFreq", "DtcsCode", "DtcsPolarity", "RxDtcsCode",
    "CrossMode", "Mode", "TStep", "Skip", "Power", "Comment",
    "URCALL", "RPT1CALL", "RPT2CALL", "DVCODE",
]


def die(msg: str, code: int = 1) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def load_config(path: Path) -> dict:
    if not path.exists():
        die(f"config file not found: {path}\n"
            f"copy config.json.sample to {path} and fill in your token / user-agent.")
    try:
        cfg = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        die(f"config file is not valid JSON: {e}")
    token = cfg.get("api_token")
    ua = cfg.get("user_agent", {})
    needed = ["app_name", "version", "url", "contact_email"]
    if not token or token == "changeme":
        die("config: api_token is missing or unset")
    for k in needed:
        if not ua.get(k) or ua[k] == "changeme":
            die(f"config: user_agent.{k} is missing or unset")
    return cfg


def build_user_agent(ua: dict) -> str:
    return f"{ua['app_name']}/{ua['version']} ({ua['url']}; {ua['contact_email']})"


def prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"{msg}{suffix}: ").strip()
        if val:
            return val
        if default is not None:
            return default


def parse_bands(s: str) -> list[str]:
    s = s.strip().lower()
    if s in ("all", "*"):
        return list(BANDS.keys())
    picked = []
    for tok in s.split(","):
        tok = tok.strip()
        if tok not in BANDS:
            die(f"unknown band '{tok}' (valid: {', '.join(BANDS)} or 'all')")
        picked.append(tok)
    return picked


def geocode(zipcode: str, country: str) -> tuple[float, float, str | None]:
    url = ZIPPO_URL.format(country=country.lower(), postal=zipcode)
    r = requests.get(url, timeout=15)
    if r.status_code == 404:
        die(f"zipcode {zipcode!r} not found in country {country!r}")
    r.raise_for_status()
    data = r.json()
    if not data.get("places"):
        die(f"no places returned for zip {zipcode}")
    place = data["places"][0]
    lat = float(place["latitude"])
    lon = float(place["longitude"])
    state_abbr = place.get("state abbreviation") or place.get("state")
    return lat, lon, state_abbr


def dist_to_bbox_miles(lat: float, lon: float, bbox: tuple[float, float, float, float]) -> float:
    minlat, maxlat, minlon, maxlon = bbox
    nlat = max(minlat, min(lat, maxlat))
    nlon = max(minlon, min(lon, maxlon))
    return haversine_miles(lat, lon, nlat, nlon)


def states_within_radius(lat: float, lon: float, radius_mi: float, origin_state: str) -> list[str]:
    picked = [origin_state]
    for abbr, bbox in STATE_BBOX.items():
        if abbr == origin_state:
            continue
        if dist_to_bbox_miles(lat, lon, bbox) <= radius_mi:
            picked.append(abbr)
    return picked


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.7613  # Earth radius in miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def fetch_repeaterbook(params: dict, token: str, user_agent: str, international: bool) -> list[dict]:
    url = RB_ROW_URL if international else RB_NA_URL
    headers = {
        "X-RB-App-Token": token,
        "User-Agent": user_agent,
        "Accept": "application/json",
    }
    for attempt in range(3):
        r = requests.get(url, params=params, headers=headers, timeout=60)
        if r.status_code == 429:
            wait = 2 ** attempt * 5
            print(f"  rate limited (429); backing off {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if r.status_code == 401 or r.status_code == 403:
            die(f"Repeaterbook returned {r.status_code}: "
                f"check that your token and User-Agent are approved. Body: {r.text[:300]}")
        r.raise_for_status()
        try:
            data = r.json()
        except ValueError:
            die(f"Repeaterbook returned non-JSON: {r.text[:300]}")
        # The API typically returns {"count": N, "results": [...]}
        if isinstance(data, dict):
            return data.get("results") or data.get("rptrList") or []
        if isinstance(data, list):
            return data
        return []
    die("Repeaterbook: giving up after repeated 429 responses")


def fget(row: dict, *keys: str, default: str = "") -> str:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return str(row[k])
    return default


def is_fm_capable(row: dict) -> bool:
    flag = fget(row, "FM Analog", "Analog Capable", "Analog").strip().lower()
    if flag in ("yes", "y", "true", "1"):
        return True
    mode = fget(row, "Operating Mode", "Mode").lower()
    return "fm" in mode or "analog" in mode


def in_any_band(freq_mhz: float, bands: list[str]) -> bool:
    for b in bands:
        lo, hi = BANDS[b]
        if lo <= freq_mhz <= hi:
            return True
    return False


def row_latlon(row: dict) -> tuple[float, float] | None:
    lat = fget(row, "Lat", "Latitude")
    lon = fget(row, "Long", "Longitude", "Lng")
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


def row_freq(row: dict) -> float | None:
    try:
        return float(fget(row, "Frequency", "Output Frequency"))
    except ValueError:
        return None


def row_input_freq(row: dict) -> float | None:
    try:
        return float(fget(row, "Input Freq", "Input Frequency"))
    except ValueError:
        return None


def compute_duplex_offset(output_mhz: float, input_mhz: float | None) -> tuple[str, float]:
    if input_mhz is None or input_mhz == 0:
        return "", 0.0
    diff = round(input_mhz - output_mhz, 6)
    if abs(diff) < 1e-6:
        return "", 0.0
    if diff > 0:
        return "+", abs(diff)
    return "-", abs(diff)


def _classify_tone(val: str) -> tuple[str, str]:
    v = (val or "").strip()
    if not v or v.upper() == "CSQ":
        return "none", ""
    if v.upper().startswith("D") and v[1:].isdigit():
        return "dcs", v[1:].zfill(3)
    try:
        float(v)
        return "ctcss", v
    except ValueError:
        return "none", ""


def tone_fields(row: dict) -> tuple[str, str, str, str, str, str, str]:
    """Return (Tone, rToneFreq, cToneFreq, DtcsCode, RxDtcsCode, DtcsPolarity, CrossMode)."""
    up_kind, up_val = _classify_tone(fget(row, "PL"))
    dn_kind, dn_val = _classify_tone(fget(row, "TSQ"))

    ctcss = up_val if up_kind == "ctcss" else (dn_val if dn_kind == "ctcss" else "88.5")
    dcs = up_val if up_kind == "dcs" else (dn_val if dn_kind == "dcs" else "023")
    polarity = "NN"

    kinds = (up_kind, dn_kind)
    if kinds == ("none", "none"):
        return "", ctcss, ctcss, dcs, dcs, polarity, "Tone->Tone"
    if kinds == ("ctcss", "none"):
        return "Tone", ctcss, ctcss, dcs, dcs, polarity, "Tone->Tone"
    if kinds in (("ctcss", "ctcss"), ("none", "ctcss")):
        return "TSQL", ctcss, ctcss, dcs, dcs, polarity, "Tone->Tone"
    if kinds in (("dcs", "none"), ("dcs", "dcs"), ("none", "dcs")):
        return "DTCS", ctcss, ctcss, dcs, dcs, polarity, "DTCS->DTCS"
    label = {"ctcss": "Tone", "dcs": "DTCS", "none": ""}
    r_tone = up_val if up_kind == "ctcss" else (dn_val if dn_kind == "ctcss" else "88.5")
    c_tone = dn_val if dn_kind == "ctcss" else r_tone
    rx_dcs = dn_val if dn_kind == "dcs" else dcs
    return "Cross", r_tone, c_tone, dcs, rx_dcs, polarity, f"{label[up_kind]}->{label[dn_kind]}"


def build_chirp_rows(repeaters: list[dict], origin: tuple[float, float], radius_mi: float,
                     bands: list[str], start_index: int) -> list[list[str]]:
    olat, olon = origin
    kept = []
    for row in repeaters:
        freq = row_freq(row)
        if freq is None:
            continue
        if not in_any_band(freq, bands):
            continue
        if not is_fm_capable(row):
            continue
        ll = row_latlon(row)
        if ll is None:
            continue
        dist = haversine_miles(olat, olon, ll[0], ll[1])
        if dist > radius_mi:
            continue
        kept.append((dist, row, freq))
    kept.sort(key=lambda x: x[0])

    out = []
    for i, (dist, row, freq) in enumerate(kept):
        loc = start_index + i
        name = fget(row, "Callsign")[:8]
        duplex, offset = compute_duplex_offset(freq, row_input_freq(row))
        tone_col, r_tone, c_tone, dtcs, rx_dtcs, polarity, cross_mode = tone_fields(row)
        city = fget(row, "Nearest City", "City", "Location")
        notes = fget(row, "Notes")
        comment_parts = [p for p in (city, f"{dist:.1f}mi", notes) if p]
        comment = " - ".join(comment_parts)
        out.append([
            str(loc),
            name,
            f"{freq:.6f}",
            duplex,
            f"{offset:.6f}",
            tone_col,
            r_tone,
            c_tone,
            dtcs,
            polarity,
            rx_dtcs,
            cross_mode,
            "FM",
            "5.00",
            "",
            "High",
            comment,
            "", "", "", "",
        ])
    return out


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CHIRP_HEADER)
        w.writerows(rows)


def gather_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export nearby Repeaterbook repeaters to a Chirp CSV.")
    p.add_argument("--zip", dest="zipcode", help="Zip / postal code")
    p.add_argument("--radius", type=float, help="Radius in miles")
    p.add_argument("--bands", help=f"Comma-separated bands: {', '.join(BANDS)} (or 'all')")
    p.add_argument("--country", default=None, help="ISO country code for geocoding (default: us)")
    p.add_argument("--output", default=None, help="Output CSV path (default: repeaters.csv)")
    p.add_argument("--config", default="config.json", help="Path to config JSON (default: config.json)")
    p.add_argument("--start-index", type=int, default=None, help="Chirp starting memory slot (default: 0)")
    return p.parse_args()


def main() -> int:
    args = gather_args()
    cfg = load_config(Path(args.config))
    user_agent = build_user_agent(cfg["user_agent"])
    token = cfg["api_token"]

    zipcode = args.zipcode or prompt("Zip / postal code")
    country = (args.country or prompt("Country code", default="us")).lower()
    radius = args.radius if args.radius is not None else float(prompt("Radius (miles)", default="30"))
    bands_str = args.bands or prompt(f"Bands ({', '.join(BANDS)}, or 'all')", default="2m,70cm")
    bands = parse_bands(bands_str)
    out_path = Path(args.output or prompt("Output file", default="repeaters.csv"))
    start_index = args.start_index if args.start_index is not None else int(prompt("Chirp starting slot", default="0"))

    print(f"geocoding {zipcode!r} ({country})...", file=sys.stderr)
    lat, lon, state_abbr = geocode(zipcode, country)
    print(f"  -> {lat:.5f}, {lon:.5f}" + (f" ({state_abbr})" if state_abbr else ""), file=sys.stderr)

    international = country != "us"
    all_rows: list[dict] = []
    seen: set[tuple[str, str]] = set()

    if international:
        country_name = cfg.get("country_name_override") or input(
            f"Repeaterbook country name for ROW endpoint [{country.upper()}]: "
        ).strip() or country.upper()
        print(f"fetching Repeaterbook (country={country_name})...", file=sys.stderr)
        rows = fetch_repeaterbook({"country": country_name}, token, user_agent, international=True)
        all_rows.extend(rows)
    else:
        if not state_abbr or state_abbr.upper() not in STATE_FIPS:
            die(f"could not determine US state from zip {zipcode} (got {state_abbr!r})")
        state_abbr = state_abbr.upper()
        states = states_within_radius(lat, lon, radius, state_abbr)
        for st in states:
            fips = STATE_FIPS.get(st)
            if not fips:
                continue
            print(f"fetching Repeaterbook (state={st}, fips={fips})...", file=sys.stderr)
            rows = fetch_repeaterbook({"state_id": fips}, token, user_agent, international=False)
            for r in rows:
                key = (fget(r, "State ID", "state_id"), fget(r, "Rptr ID", "repeater_id", "rptrId"))
                if key in seen:
                    continue
                seen.add(key)
                all_rows.append(r)

    print(f"total repeaters fetched: {len(all_rows)}", file=sys.stderr)
    chirp_rows = build_chirp_rows(all_rows, (lat, lon), radius, bands, start_index)
    print(f"matching (FM, band, within {radius}mi): {len(chirp_rows)}", file=sys.stderr)
    write_csv(out_path, chirp_rows)
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
