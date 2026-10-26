# Puxa Apto

Requires Python 3.10+ (the repo pins 3.12.1 in `.python-version`).

```bash
cd puxa-apto
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Development Installation

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest      # offline; the network is replaced by tests/fixtures
```

## Usage

A search is a JSON file in `buscas/`:

```bash
puxa-apto scrape -C buscas/famed-ufrgs.json      # rent near UFRGS Faculdade de Medicina
puxa-apto scrape -C buscas/curitiba-venda.json   # the original Curitiba search
```

Without `-C`, `./puxa-apto.json` is used if it exists (or the path in `PUXA_CONFIG`).

A search has two parts:

- **Map area** (`center` + `radius_km`): VivaReal and Zap search inside that box.
- **Neighborhoods** (`neighborhoods`, needs `state` and `city`): Chaves na Mão and ImovelWeb
  search those neighborhoods.

A site with neither is skipped. `urls.<site>` in the config, or `--<site>-url` on the command
line, replaces the built URLs for that site.

Filters (`max_price`, `min_area`, `bedrooms`, `exclude_neighborhoods`) are sent to VivaReal/Zap
and also applied to every scraped listing. A listing whose value couldn't be read is kept.

### Overriding a search

Command-line flags beat `PUXA_*` environment variables, which beat `.env`, which beats the
config file:

```bash
puxa-apto scrape -C buscas/famed-ufrgs.json --max-price 3000 -q 1 -q 2
PUXA_MAX_PRICE=2500 puxa-apto scrape -C buscas/famed-ufrgs.json
puxa-apto scrape -t aluguel --center=-30.0400,-51.2076 -r 1.5
```

Lists from env vars are JSON (`PUXA_BEDROOMS='[1,2]'`); nested fields use `__`
(`PUXA_CENTER__LAT=-30.04`).

### Options

- `--config`, `-C`: search config JSON
- `--transaction`, `-t`: `aluguel` or `venda`
- `--center`: `LAT,LON`; write it as `--center=-30.04,-51.21` because it starts with `-`
- `--radius-km`, `-r`
- `--neighborhood`, `-b` (repeatable)
- `--exclude-neighborhood`, `-x` (repeatable; accents and case are ignored)
- `--max-price`, `-p`
- `--min-area`, `-a`
- `--bedrooms`, `-q` (repeatable)
- `--vivareal-url`, `-v` / `--chaves-url`, `-c` / `--imovelweb-url`, `-i` / `--zap-url`, `-z`
  (repeatable)
- `--json`, `-j` (default: `apartamentos.json`)
- `--csv` (default: timestamped filename)
- `--max-pages`, `-m`: per search URL
- `--verbose`, `-V`
- `--skip-vivareal`, `--skip-chaves`, `--skip-imovelweb`, `--skip-zap`

## Duplicate Detection

1. **Link-based detection**: Exact URL matches
2. **Fingerprint-based detection**: Based on street, neighborhood, area, bedrooms, and price