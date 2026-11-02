# Configuration

You probably want puxa-apto to run one particular search: rentals near a hospital, say, or
three-bedroom apartments for sale in a few Curitiba neighborhoods. That search is a JSON file,
and you hand it over with `-C`. This is the one the repo ships for apartments near the UFRGS
medical school:

```json
{
  "transaction": "aluguel",
  "state": "RS",
  "city": "Porto Alegre",
  "places": [
    {"name": "Famed", "lat": -30.0400303, "lon": -51.2075511}
  ],
  "radius_km": 1.2,
  "neighborhoods": ["Santa Cecília", "Rio Branco", "Bom Fim", "Santana", "Farroupilha", "Independência", "Moinhos de Vento", "Jardim Botânico"],
  "exclude_neighborhoods": ["Centro Histórico"],
  "json_file": "famed-ufrgs-v2.json"
}
```

```bash
puxa-apto scrape -C buscas/famed-ufrgs.json
```

Every key in that file can also be set for a single run with an environment variable, and most
of them with a flag.

## Where settings come from

When the same setting shows up in more than one place, the first of these wins:

1. command-line flag
2. `PUXA_*` environment variable
3. `.env` in the working directory
4. config file
5. built-in default

puxa-apto picks the config file like this: `--config`/`-C` if you pass it, otherwise the path in
`PUXA_CONFIG`, otherwise `./puxa-apto.json` if that file exists. If none of those apply, there's
no file, and only flags, environment variables and defaults count. A config path that doesn't
exist prints `Config file not found: <path>` and exits with code 2.

Repeatable flags (`--place`, `-b`, `-x`, `-q` and the `--<site>-url` flags) build a list that
replaces the configured one instead of adding to it. `-q 1` on top of `"bedrooms": [2, 3]` keeps
1-bedroom listings only.

Be careful with typos in the config file. Keys puxa-apto doesn't know are ignored without a
warning, so `"max_prise": 2500` does nothing and you'll still get listings above 2500. The same
goes for an unknown site under `urls`.

A known key with a bad value, such as `"radius_km": 0`, prints `Invalid configuration:` followed
by the validation error and exits with code 2. If none of the selected sites has anything to
search, the run prints `Nothing to search: ...` and also exits with code 2.

Some overrides on top of a config file, and one search built from flags alone:

```bash
puxa-apto scrape -C buscas/famed-ufrgs.json --max-price 3000 -q 1 -q 2
PUXA_MAX_PRICE=2500 puxa-apto scrape -C buscas/famed-ufrgs.json
puxa-apto scrape -t aluguel --place "HCPA=-30.0387,-51.2066" -r 1.5 --max-total 2000
```

## Environment variables

The name is `PUXA_` plus the key in upper case, for example `PUXA_MAX_PRICE`. Names are matched
without regard to case.

Lists and objects are written as JSON:

```bash
PUXA_BEDROOMS='[1,2]'
PUXA_PLACES='[{"name": "HCPA", "lat": -30.0387, "lon": -51.2066}]'
```

Nested keys use `__`, as in `PUXA_URLS__ZAP='["https://..."]'`.

A `.env` file in the working directory uses the same names, one `NAME=value` per line. Lines
whose name doesn't start with `PUXA_` are ignored.

## Settings

| Key | Type | Default | Flag | Env var |
|---|---|---|---|---|
| `transaction` | `"aluguel"` or `"venda"` | `"venda"` | `--transaction`, `-t` | `PUXA_TRANSACTION` |
| `state` | string (UF) | none | none | `PUXA_STATE` |
| `city` | string | none | none | `PUXA_CITY` |
| `places` | list of `{"name", "lat", "lon"}` | `[]` | `--place NAME=LAT,LON` | `PUXA_PLACES` |
| `radius_km` | number > 0 | `1.2` | `--radius-km`, `-r` | `PUXA_RADIUS_KM` |
| `neighborhoods` | list of strings | `[]` | `--neighborhood`, `-b` | `PUXA_NEIGHBORHOODS` |
| `exclude_neighborhoods` | list of strings | `[]` | `--exclude-neighborhood`, `-x` | `PUXA_EXCLUDE_NEIGHBORHOODS` |
| `max_price` | number | none | `--max-price`, `-p` | `PUXA_MAX_PRICE` |
| `max_total` | number > 0 | none | `--max-total`, `-T` | `PUXA_MAX_TOTAL` |
| `min_area` | integer (m²) | none | `--min-area`, `-a` | `PUXA_MIN_AREA` |
| `bedrooms` | list of integers | `[]` | `--bedrooms`, `-q` | `PUXA_BEDROOMS` |
| `sites` | list of site keys, at least one | all six | `--skip-<site>` removes one for a run | `PUXA_SITES` |
| `urls` | object: site key → list of URLs | `{}` | `--<site>-url` | `PUXA_URLS__<SITE>` |
| `max_pages` | integer | none (no limit) | `--max-pages`, `-m` | `PUXA_MAX_PAGES` |
| `json_file` | path | `"apartamentos.json"` | `--json`, `-j` | `PUXA_JSON_FILE` |
| `csv_file` | path | none | `--csv` | `PUXA_CSV_FILE` |
| `xlsx_file` | path (`.xlsx`) | none | `--xlsx` | `PUXA_XLSX_FILE` |
| `title` | string | `"<Aluguel\|Venda> · <city>"` | none | `PUXA_TITLE` |

### `transaction`

`"venda"` (sale) or `"aluguel"` (rent). Any other value is an invalid configuration. Every site's
search URL carries it. Certa only rents, so Certa is skipped when this is `"venda"`.

```json
{
  "transaction": "aluguel",
  "places": [{"name": "Famed", "lat": -30.0400303, "lon": -51.2075511}]
}
```

### `state`

The two-letter state code (UF), such as `"RS"` or `"PR"`. Required whenever `neighborhoods` is
set; without it the run fails with `state and city are required when neighborhoods are set`.
Chaves na Mão puts it in its search URL. Leindecker and Certa run only when it is `RS` (any case)
and `city` is Porto Alegre.

```json
{
  "state": "RS",
  "city": "Porto Alegre",
  "neighborhoods": ["Bom Fim", "Santana"]
}
```

### `city`

The city name, such as `"Porto Alegre"`. Required whenever `neighborhoods` is set, with the same
error as `state`. Chaves na Mão and ImovelWeb put it in their search URLs. Leindecker and Certa
run only when it is Porto Alegre and `state` is RS. Accents and case are ignored for this check,
so `"porto alegre"` works.

```json
{
  "transaction": "venda",
  "state": "PR",
  "city": "Curitiba",
  "neighborhoods": ["Água Verde", "Batel", "Bigorrilho"]
}
```

### `places`

Reference points, each with a `name`, a `lat` and a `lon`.

- VivaReal and Zap search one map box that covers `radius_km` around every place. Without
  places they have nothing to search.
- Each saved listing gets one `distance_km_<name>` per place and `distance_km` to the nearest
  one. The name is slugified with `_`, so `Campus Saúde` becomes `distance_km_campus_saude`.
- Names must contain a letter or digit and must be unique after slugifying, so `HCPA` and `hcpa`
  can't both appear.
- `lat` must be between -90 and 90, `lon` between -180 and 180.
- On the command line, `--place "HCPA=-30.0387,-51.2066"` adds one place and can be repeated.
  Places given this way replace the config's places. A malformed value exits with code 2.

```json
{
  "transaction": "aluguel",
  "places": [
    {"name": "HCPA", "lat": -30.0386784, "lon": -51.2066248},
    {"name": "Campus Saúde", "lat": -30.0402784, "lon": -51.2065759}
  ]
}
```

### `radius_km`

The radius in kilometers, greater than 0. It sets the size of the VivaReal/Zap map box. With
`places` set, it also drops listings farther than `radius_km` from every place, and drops
listings without coordinates because their distance is unknown. Without `places` it has no
effect.

```json
{
  "transaction": "aluguel",
  "places": [{"name": "Famed", "lat": -30.0400303, "lon": -51.2075511}],
  "radius_km": 2
}
```

### `neighborhoods`

Neighborhood names. Chaves na Mão runs one search per neighborhood and ImovelWeb runs one search
for all of them. In Porto Alegre, Leindecker and Certa search them too. Requires `state` and
`city`. On the command line, `-b` can be repeated and replaces the configured list.

```json
{
  "transaction": "aluguel",
  "state": "RS",
  "city": "Porto Alegre",
  "neighborhoods": ["Santa Cecília", "Rio Branco", "Bom Fim", "Santana"]
}
```

### `exclude_neighborhoods`

Drops listings whose neighborhood matches one of these, ignoring accents and case. It is applied
only after scraping and is never sent to a site.

```json
{
  "transaction": "aluguel",
  "places": [{"name": "Famed", "lat": -30.0400303, "lon": -51.2075511}],
  "exclude_neighborhoods": ["Centro Histórico"]
}
```

### `max_price`

Drops listings priced above it: the rent for `aluguel`, the sale price for `venda`. A listing
whose price is unknown is kept. The smaller of `max_price` and `max_total` is sent to every site
as its price cap.

```json
{
  "transaction": "venda",
  "state": "PR",
  "city": "Curitiba",
  "neighborhoods": ["Água Verde", "Batel"],
  "max_price": 750000
}
```

### `max_total`

Caps the price plus condo fee and must be greater than 0. Listings above it are dropped; a
missing fee counts as 0 and a listing with an unknown price is kept. The smaller of `max_price`
and `max_total` is sent to every site as its price cap, so fewer pages are fetched.

```json
{
  "transaction": "aluguel",
  "places": [{"name": "Famed", "lat": -30.0400303, "lon": -51.2075511}],
  "max_total": 2500
}
```

### `min_area`

The minimum area in square meters. It drops smaller listings and is sent to every site. A
listing whose area is unknown is kept.

```json
{
  "transaction": "aluguel",
  "places": [{"name": "Famed", "lat": -30.0400303, "lon": -51.2075511}],
  "min_area": 40
}
```

### `bedrooms`

The bedroom counts to keep. A listing whose count is unknown is kept. Each site receives this
differently; see [What each site searches with](#what-each-site-searches-with).

```json
{
  "transaction": "aluguel",
  "places": [{"name": "Famed", "lat": -30.0400303, "lon": -51.2075511}],
  "bedrooms": [1, 2]
}
```

### `sites`

Which sites run, by key: `vivareal`, `chaves`, `imovelweb`, `zap`, `leindecker`, `certa`. They
always run in that order, whatever the order of the list. An unknown key or an empty list is an
invalid configuration. `--skip-<site>` drops one site for a single run. A listed site still needs
something to search; see [Sites](#sites).

```json
{
  "transaction": "aluguel",
  "state": "RS",
  "city": "Porto Alegre",
  "neighborhoods": ["Bom Fim", "Santana"],
  "sites": ["chaves", "imovelweb"]
}
```

### `urls`

Explicit search URLs per site, which replace the URLs built from `places` and `neighborhoods`.
A `--<site>-url` flag beats `urls.<site>`. Leindecker and Certa URLs must end with their page
number, such as `.../1/`. A site still has to be in `sites` to run.

```json
{
  "transaction": "venda",
  "sites": ["vivareal", "zap"],
  "urls": {
    "vivareal": ["https://www.vivareal.com.br/venda/brasil/apartamento_residencial/?transacao=venda&stamps=Datazap&tipos=apartamento_residencial&amenities=Portaria+24h&quartos=3%2C4&precoMaximo=750000&areaMinima=85&viewport=-49.266843766513205%2C-25.411754369023587%7C-49.31962963992629%2C-25.47151235294528"],
    "zap": ["https://www.zapimoveis.com.br/venda/?transacao=venda&stamps=Datazap&amenities=Portaria+24h&quartos=3%2C4&precoMaximo=750000&areaMinima=85&viewport=-49.26565732569504%2C-25.408943548379348%7C-49.318443199108124%2C-25.46870292652639"]
  }
}
```

### `max_pages`

Pages fetched per search URL. Unset or `0` means keep going until the site has no next page.

```json
{
  "transaction": "aluguel",
  "places": [{"name": "Famed", "lat": -30.0400303, "lon": -51.2075511}],
  "max_pages": 3
}
```

### `json_file`

The accumulated history. New listings are appended to it. Links, fingerprints and agency codes
already in it are never saved again. A relative path is resolved from the working directory.

```json
{
  "transaction": "aluguel",
  "places": [{"name": "Famed", "lat": -30.0400303, "lon": -51.2075511}],
  "json_file": "famed.json"
}
```

### `csv_file`

When set, every run that finds new listings appends them to this CSV.

- A missing or empty file gets the header first. After that, the header and column order are
  never rewritten or reordered.
- Running the same command twice adds nothing the second time, because listings already in the
  JSON or in the CSV aren't new.
- Pointing `--csv` at a fresh file on each run gives a file with only that run's new listings.
- If the existing file's columns differ from the run's (for example after changing `places`,
  which changes the `distance_km_<place>` columns), the file is left untouched. The new listings
  go to `<name>_<YYYYMMDD_HHMMSS>.csv` next to it, and the console prints
  `... has different columns; new listings saved to ...`.
- When unset, each such run writes `apartamentos_novos_<YYYYMMDD_HHMMSS>.csv` with only that
  run's new listings, unless `xlsx_file` is set: the Excel sheet then replaces that default CSV.

The existing CSV (`csv_file`, or `apartamentos.csv` when unset) is also read to skip duplicates.

```json
{
  "transaction": "aluguel",
  "places": [{"name": "Famed", "lat": -30.0400303, "lon": -51.2075511}],
  "json_file": "famed.json",
  "csv_file": "famed.csv"
}
```

### `xlsx_file`

When set, every run that finds new listings adds one sheet with them to this Excel workbook,
creating the workbook if it is missing. The file opens in Google Sheets, Excel and ONLYOFFICE.

- The sheet is named after the day (`DD-MM`; a second run that day gets `DD-MM (2)`) and becomes
  the first tab. Existing sheets, and whatever you typed in them, are kept.
- Rows are sorted by total, cheapest first. Each column has a filter: checkboxes for Bairro,
  "Number filters" (between, ≥, ≤) for the Distância columns, Total, Aluguel, Condomínio,
  IPTU, Área, Quartos, Banh. and Vagas, and "contains" for Rua. A blank cell means the site
  didn't say, so "Vagas ≥ 1" hides listings without parking information.
- Row 1 counts the rows the filters leave visible.
- Categoria is a dropdown (Favoritado, Em andamento, Talvez, Descartado) that colours the row.
  Its choices live on a hidden `Listas` sheet; keep it.
- With `places`, each place gets a `Distância até <place>` column, in whole metres, so a filter
  reads "≥ 500". With 2 or more places, a `Distância (mais próxima)` column comes first: the
  distance `radius_km` filters on. Closest rows are greenest.
- Comodidades translates `amenity_codes` to Portuguese.
- The path is checked before scraping: a non-`.xlsx` name, a missing folder or a file that isn't
  a readable workbook stops the run with exit code 2.
- The sheet is written before the JSON history. If writing it fails, nothing is saved and the
  run exits with code 1, so rerunning retries the same listings.
- With `xlsx_file` set, the default timestamped CSV is not written; set `csv_file` to keep a CSV.

```json
{
  "transaction": "aluguel",
  "places": [{"name": "Famed", "lat": -30.0400303, "lon": -51.2075511}],
  "json_file": "famed.json",
  "xlsx_file": "famed.xlsx"
}
```

### `title`

The heading in cell A1 of each Excel sheet. Default: `Aluguel · <city>` or `Venda · <city>`
(without the city when `city` is unset).

```json
{
  "transaction": "aluguel",
  "city": "Porto Alegre",
  "title": "Aluguel perto da FAMED · UFRGS",
  "xlsx_file": "famed.xlsx"
}
```

## Sites

| Site | Key | Host | URL flag | Skip flag |
|---|---|---|---|---|
| VivaReal | `vivareal` | vivareal.com.br | `--vivareal-url`, `-v` | `--skip-vivareal` |
| Chaves na Mão | `chaves` | chavesnamao.com.br | `--chaves-url`, `-c` | `--skip-chaves` |
| ImovelWeb | `imovelweb` | imovelweb.com.br | `--imovelweb-url`, `-i` | `--skip-imovelweb` |
| Zap Imóveis | `zap` | zapimoveis.com.br | `--zap-url`, `-z` | `--skip-zap` |
| Leindecker | `leindecker` | leindecker.com.br | `--leindecker-url` | `--skip-leindecker` |
| Certa | `certa` | certa.com.br | `--certa-url` | `--skip-certa` |

### What each site searches with

| Site | Runs when | Price cap | `min_area` | `bedrooms` |
|---|---|---|---|---|
| VivaReal | `places` is set | yes | yes | every value |
| Zap Imóveis | `places` is set | yes | yes | every value |
| Chaves na Mão | `neighborhoods` is set | yes | yes | not sent |
| ImovelWeb | `neighborhoods` is set | yes | yes | only when exactly one value is given (the site reads it as "exactly N") |
| Leindecker | `neighborhoods` is set in Porto Alegre, RS | yes | yes | the smallest value (the site reads it as "N or more") |
| Certa | `neighborhoods` is set in Porto Alegre, RS, and `transaction` is `aluguel` | yes | yes | the smallest value (the site reads it as "N or more") |

A site with URLs in `urls` or a `--<site>-url` flag runs regardless of this table. The filters
apply to every listing after scraping anyway, so whatever a site doesn't receive is still
enforced.

## Command-line only

- `--config`, `-C`: the config file. See [Where settings come from](#where-settings-come-from).
- `--verbose`, `-V`: debug logging.
- `puxa-apto info`: lists the supported sites.
- `puxa-apto export-xlsx <listings.json|.csv> -o <workbook.xlsx>`: adds a sheet of listings that
  were already saved (a `json_file` history or a CSV written by `scrape`) to a workbook, as
  [`xlsx_file`](#xlsx_file) does. `-C <config>` takes the sheet's title and place names from a
  search; without it, column labels come from the file's `distance_km_<place>` keys.
  `-n <name>` names the sheet (default: the file's date, `DD-MM`). Exits 2 when the workbook
  can't be written.

## Examples

Rent within 1 km of either hospital, at most R$ 2,500 with the condo fee, one or two bedrooms:

```json
{
  "transaction": "aluguel",
  "places": [
    {"name": "HCPA", "lat": -30.0386784, "lon": -51.2066248},
    {"name": "HPS", "lat": -30.0369333, "lon": -51.2098087}
  ],
  "radius_km": 1,
  "max_total": 2500,
  "bedrooms": [1, 2],
  "json_file": "hospitais.json"
}
```

Porto Alegre neighborhoods on Chaves na Mão and the two agencies only, never Centro Histórico:

```json
{
  "transaction": "aluguel",
  "state": "RS",
  "city": "Porto Alegre",
  "neighborhoods": ["Bom Fim", "Santana", "Farroupilha", "Rio Branco"],
  "exclude_neighborhoods": ["Centro Histórico"],
  "sites": ["chaves", "leindecker", "certa"],
  "max_price": 2200,
  "json_file": "poa-bairros.json"
}
```

Fixed search URLs copied from the sites' own search pages, for sale in Curitiba (adapted from
`buscas/curitiba-venda.json`):

```json
{
  "transaction": "venda",
  "state": "PR",
  "city": "Curitiba",
  "max_price": 750000,
  "min_area": 85,
  "bedrooms": [3, 4],
  "sites": ["vivareal", "chaves", "imovelweb", "zap"],
  "urls": {
    "vivareal": ["https://www.vivareal.com.br/venda/brasil/apartamento_residencial/?transacao=venda&stamps=Datazap&tipos=apartamento_residencial&amenities=Portaria+24h&quartos=3%2C4&precoMaximo=750000&areaMinima=85&viewport=-49.266843766513205%2C-25.411754369023587%7C-49.31962963992629%2C-25.47151235294528"],
    "chaves": ["https://www.chavesnamao.com.br/apartamentos-a-venda/pr-curitiba/agua-verde/3-quartos/?filtro=bai%3A[8629+8669+8628+8637+8646+8662]%2Cpmax%3A750000%2Camin%3A85%2Care%3A[31]"],
    "imovelweb": ["https://www.imovelweb.com.br/apartamentos-venda-agua-verde-curitiba-batel-curitiba-bigorrilho-portao-curitiba-areac-portaria-24-horas-3-quartos-mais-85-m2-util-menos-750000-reales-ordem-publicado-maior.html"],
    "zap": ["https://www.zapimoveis.com.br/venda/?transacao=venda&stamps=Datazap&amenities=Portaria+24h&quartos=3%2C4&precoMaximo=750000&areaMinima=85&viewport=-49.26565732569504%2C-25.408943548379348%7C-49.318443199108124%2C-25.46870292652639"]
  }
}
```
