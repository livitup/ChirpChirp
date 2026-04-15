# ChirpChirp

Download Repeaterbook data by zipcode + radius and export a [Chirp](https://chirpmyradio.com/)-compatible CSV.

## Setup

```sh
pip install -r requirements.txt
cp config.json.sample config.json
# edit config.json with your approved Repeaterbook API token and User-Agent info
```

## Usage

```sh
python chirpchirp.py --zip 07030 --radius 30 --bands 2m,70cm --output repeaters.csv
```

Any missing argument is prompted for interactively.

### Arguments

| Flag | Description |
| --- | --- |
| `--zip` | Postal / zip code |
| `--radius` | Radius in miles |
| `--bands` | Comma-separated: `2m`, `1.25m`, `70cm`, `33cm` (or `all`) |
| `--country` | ISO country code for geocoding (default `us`) |
| `--output` | Output CSV path (default `repeaters.csv`) |
| `--config` | Path to config JSON (default `config.json`) |
| `--start-index` | Starting Chirp memory slot number (default `0`) |

Only FM-capable repeaters are included. Distance filtering is client-side; for US zips, the adjacent states are also queried so border repeaters aren't missed.
