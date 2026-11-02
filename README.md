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
.venv/bin/python -m pytest -n auto  # offline; the network is replaced by tests/fixtures
```

Code-quality sensors and agent workflow: see AGENTS.md.

## Usage

A search is a JSON file in `buscas/`:

```bash
puxa-apto scrape -C buscas/famed-ufrgs.json      # rent near UFRGS Faculdade de Medicina
puxa-apto scrape -C buscas/curitiba-venda.json   # the original Curitiba search
```

Without `-C`, `./puxa-apto.json` is used if it exists (or the path in `PUXA_CONFIG`).

A search is a set of places (reference points that VivaReal and Zap search around) plus a list
of neighborhoods (searched by Chaves na Mão, ImovelWeb and, in Porto Alegre, the agencies
Leindecker and Certa). Filters such as `max_price` or `bedrooms` then drop listings that don't
match. Settings come from the JSON file, command-line flags and `PUXA_*` environment variables.
Every setting, flag and environment variable is described in [docs/configuration.md](docs/configuration.md).

Each saved listing gets `total_price`, `distance_km` (to the nearest place), one
`distance_km_<place>` per place (e.g. `distance_km_campus_saude`), and, where the site provides
them, `description` and raw `amenity_codes` (VivaReal/Zap, e.g. `CONCIERGE_24H`, `GAS_SHOWER`;
Leindecker/Certa, e.g. `Portaria 24hrs`). Leindecker and Certa listings get their detail page
fetched (condo fee, IPTU, street, description, amenities), one request each.
`approximate_location` is `true` when VivaReal/Zap hide the address and only give a rounded
point; its distances are then estimates, typically within ~100 m but sometimes far off.

Add `--xlsx busca.xlsx` (or `"xlsx_file"` in the search) to get each run's new listings as a
filterable Excel sheet; `puxa-apto export-xlsx <file.json|file.csv> -o busca.xlsx` converts
listings already saved. See [docs/configuration.md](docs/configuration.md#xlsx_file).

## Adding a site

1. Write `puxa_apto/scrapers/<key>.py`. A portal subclasses `BaseScraper` and implements
   `find_listing_elements` and `scrape_apartment`, overriding `get_next_page_url`,
   `has_next_page` or `page_details` where the site differs. An agency on the Leindecker/Certa
   platform subclasses `AgencyScraper`, sets `site` and `card_selector`, and implements
   `parse_card` and `parse_detail`. Export the class from `puxa_apto/scrapers/__init__.py`.
2. Add `<key>_urls(settings)` to `puxa_apto/search.py`. It returns `[]` when the search lacks
   what the site needs.
3. Add a `Site(...)` entry to `SITES` in `puxa_apto/sites.py`. `--<key>-url`, `--skip-<key>`,
   `sites`, `urls.<key>` and `PUXA_URLS__<KEY>` then work without more code.
4. Save a gzipped search results page as `tests/fixtures/<key>.html.gz` (plus
   `<key>-detail.html.gz` if the scraper fetches detail pages). The test suite then requires
   listings from it.
5. Add the site to the two site tables in `docs/configuration.md`.

Why it works this way: [docs/adr/0001-central-site-registry.md](docs/adr/0001-central-site-registry.md).

## Duplicate Detection

1. **Link-based detection**: Exact URL matches
2. **Fingerprint-based detection**: Based on street, neighborhood, area, bedrooms, and price
3. **Agency code**: a Leindecker or Certa listing cross-posted on VivaReal/Zap carries the same
   `agency_ref` (e.g. `certa:2270`). Within a run only the agency's own copy is kept (gaps such
   as coordinates are filled from the portal copy); across runs a saved ref, or a saved portal
   copy of it, blocks the listing.