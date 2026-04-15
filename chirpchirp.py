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

STATE_ADJACENCY = {
    "AL": ["FL", "GA", "TN", "MS"],
    "AK": [],
    "AZ": ["CA", "NV", "UT", "NM", "CO"],
    "AR": ["MO", "TN", "MS", "LA", "TX", "OK"],
    "CA": ["OR", "NV", "AZ"],
    "CO": ["WY", "NE", "KS", "OK", "NM", "AZ", "UT"],
    "CT": ["NY", "MA", "RI"],
    "DE": ["MD", "PA", "NJ"],
    "DC": ["MD", "VA"],
    "FL": ["GA", "AL"],
    "GA": ["FL", "AL", "TN", "NC", "SC"],
    "HI": [],
    "ID": ["WA", "OR", "NV", "UT", "WY", "MT"],
    "IL": ["WI", "IA", "MO", "KY", "IN"],
    "IN": ["MI", "OH", "KY", "IL"],
    "IA": ["MN", "WI", "IL", "MO", "NE", "SD"],
    "KS": ["NE", "MO", "OK", "CO"],
    "KY": ["IL", "IN", "OH", "WV", "VA", "TN", "MO"],
    "LA": ["TX", "AR", "MS"],
    "ME": ["NH"],
    "MD": ["DE", "PA", "WV", "VA", "DC"],
    "MA": ["NH", "VT", "NY", "CT", "RI"],
    "MI": ["WI", "IN", "OH", "MN"],
    "MN": ["ND", "SD", "IA", "WI", "MI"],
    "MS": ["TN", "AL", "LA", "AR"],
    "MO": ["IA", "IL", "KY", "TN", "AR", "OK", "KS", "NE"],
    "MT": ["ID", "WY", "SD", "ND"],
    "NE": ["SD", "IA", "MO", "KS", "CO", "WY"],
    "NV": ["OR", "ID", "UT", "AZ", "CA"],
    "NH": ["VT", "MA", "ME"],
    "NJ": ["NY", "PA", "DE"],
    "NM": ["CO", "OK", "TX", "AZ", "UT"],
    "NY": ["VT", "MA", "CT", "NJ", "PA"],
    "NC": ["VA", "TN", "GA", "SC"],
    "ND": ["MN", "SD", "MT"],
    "OH": ["MI", "PA", "WV", "KY", "IN"],
    "OK": ["KS", "MO", "AR", "TX", "NM", "CO"],
    "OR": ["WA", "ID", "NV", "CA"],
    "PA": ["NY", "NJ", "DE", "MD", "WV", "OH"],
    "RI": ["CT", "MA"],
    "SC": ["NC", "GA"],
    "SD": ["ND", "MN", "IA", "NE", "WY", "MT"],
    "TN": ["KY", "VA", "NC", "GA", "AL", "MS", "AR", "MO"],
    "TX": ["NM", "OK", "AR", "LA"],
    "UT": ["ID", "WY", "CO", "NM", "AZ", "NV"],
    "VT": ["NY", "MA", "NH"],
    "VA": ["NC", "TN", "KY", "WV", "MD", "DC"],
    "WA": ["ID", "OR"],
    "WV": ["OH", "PA", "MD", "VA", "KY"],
    "WI": ["MN", "IA", "IL", "MI"],
    "WY": ["MT", "SD", "NE", "CO", "UT", "ID"],
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
        states = [state_abbr] + STATE_ADJACENCY.get(state_abbr, [])
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
