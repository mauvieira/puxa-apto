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

- **Places** (`places`: a list of `{"name", "lat", "lon"}` reference points) and `radius_km`:
  VivaReal and Zap search a box covering `radius_km` around every place.
- **Neighborhoods** (`neighborhoods`, needs `state` and `city`): Chaves na Mão and ImovelWeb
  search those neighborhoods. In Porto Alegre (`"city": "Porto Alegre", "state": "RS"`), the
  agencies Leindecker and Certa search them too (Certa rents only).

A site with neither is skipped. `sites` in the config (e.g. `["certa", "zap"]`; default: all of
`vivareal`, `chaves`, `imovelweb`, `zap`, `leindecker`, `certa`) chooses which sites run.
`urls.<site>` in the config, or `--<site>-url` on the command line, replaces the built URLs for
that site; Leindecker and Certa URLs must end with their page number, e.g. `.../1/`.

Filters (`max_price`, `max_total`, `min_area`, `bedrooms`, `exclude_neighborhoods`) are applied
to every scraped listing. `max_total` caps rent plus condo fee (a missing fee counts as 0). The
price cap and `min_area` are also sent to every site's search, so fewer pages are fetched.
With places set, listings farther than `radius_km` from all of them are dropped, and so are
listings without coordinates (their distance is unknown). Any other value that couldn't be read
(price, area, ...) keeps the listing.

Each saved listing gets `total_price`, `distance_km` (to the nearest place), one
`distance_km_<place>` per place (e.g. `distance_km_campus_saude`), and, where the site provides
them, `description` and raw `amenity_codes` (VivaReal/Zap, e.g. `CONCIERGE_24H`, `GAS_SHOWER`;
Leindecker/Certa, e.g. `Portaria 24hrs`). Leindecker and Certa listings get their detail page
fetched (condo fee, IPTU, street, description, amenities), one request each.
`approximate_location` is `true` when VivaReal/Zap hide the address and only give a rounded
point; its distances are then estimates, typically within ~100 m but sometimes far off.

### Overriding a search

Command-line flags beat `PUXA_*` environment variables, which beat `.env`, which beats the
config file:

```bash
puxa-apto scrape -C buscas/famed-ufrgs.json --max-price 3000 -q 1 -q 2
PUXA_MAX_PRICE=2500 puxa-apto scrape -C buscas/famed-ufrgs.json
puxa-apto scrape -t aluguel --place "HCPA=-30.0387,-51.2066" -r 1.5 --max-total 2000
```

Lists from env vars are JSON (`PUXA_BEDROOMS='[1,2]'`); nested fields use `__`
(`PUXA_URLS__ZAP='["https://..."]'`).

### Options

- `--config`, `-C`: search config JSON
- `--transaction`, `-t`: `aluguel` or `venda`
- `--place`: `NAME=LAT,LON` (repeatable; replaces the config's places)
- `--radius-km`, `-r`: keep listings within this distance of any place
- `--neighborhood`, `-b` (repeatable)
- `--exclude-neighborhood`, `-x` (repeatable; accents and case are ignored)
- `--max-price`, `-p`
- `--max-total`, `-T`: rent + condo fee
- `--min-area`, `-a`
- `--bedrooms`, `-q` (repeatable)
- `--vivareal-url`, `-v` / `--chaves-url`, `-c` / `--imovelweb-url`, `-i` / `--zap-url`, `-z` /
  `--leindecker-url` / `--certa-url` (repeatable)
- `--json`, `-j` (default: `apartamentos.json`)
- `--csv`: a CSV copy of the whole `--json` file, rewritten on every run with new listings
  (default: `apartamentos_novos_<timestamp>.csv` with only this run's new listings)
- `--max-pages`, `-m`: per search URL
- `--verbose`, `-V`
- `--skip-vivareal`, `--skip-chaves`, `--skip-imovelweb`, `--skip-zap`, `--skip-leindecker`,
  `--skip-certa`

## Duplicate Detection

1. **Link-based detection**: Exact URL matches
2. **Fingerprint-based detection**: Based on street, neighborhood, area, bedrooms, and price
3. **Agency code**: a Leindecker or Certa listing cross-posted on VivaReal/Zap carries the same
   `agency_ref` (e.g. `certa:2270`). Within a run only the agency's own copy is kept (gaps such
   as coordinates are filled from the portal copy); across runs a saved ref, or a saved portal
   copy of it, blocks the listing.