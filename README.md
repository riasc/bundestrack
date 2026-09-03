# bundestrack

Tracks roll-call votes (*Namentliche Abstimmungen*) in the German Bundestag and
computes voting/attendance statistics per member and per fraction.

**Explore the data:** https://riasc.github.io/bundestrack/

## Setup

```
mamba env create -f environment.yml
mamba activate bundestrack
```

## Usage

```
python bundestrack/main.py --period 21
```

Options:
- `--period` — legislative period (20, 21, ...), default 20
- `--start` / `--end` — ISO dates (`YYYY-MM-DD`) to restrict the vote range

## Data layout

For each period under `data/<period>/`:
- `abstimmungen/` — raw roll-call vote files (`.xlsx`, one per Abstimmung)
- `abgeordneten.txt` — member → fraction mapping
- `altnames.txt` — alternative name spellings across files
- `membervotes.csv` — per-member vote counts, ratios, and day-level attendance
- `partyvotes.csv` — same, aggregated per fraction (votes attributed to the
  fraction a member belonged to at the time of each vote, not their
  current/final one)
- `sitzverteilung.csv` — fraction sizes per vote date (these shift within a
  period due to defections/splits)

Each CSV starts with `#`-commented lines explaining its columns.

Running `main.py` also regenerates the JSON copies of this data under
`docs/data/`, which power the GitHub Pages explorer above.
