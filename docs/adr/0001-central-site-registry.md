# Central site registry

## Status

Accepted, 2026-11-01.

## Context and problem statement

Adding a scraped site meant repeating its key in about 7 places. `settings.py` had it in `SiteName` and `SiteUrls`. `search.py` had it in `_URL_BUILDERS` and `SITES`. `cli.py` had the `SCRAPERS` dict, two hand-written Typer options per site, the `cli_urls` and `skipped` dicts, the skip hint and the `info` list. The tests had `SITE_HOSTS`, `AGENCY_HOSTS` and the fixture map. Missing one of them failed late, or not at all.

How do we make a site a single entry that the rest of the code follows?

## Considered options

1. A registry whose entries also generate the CLI flags.
2. A registry with hand-written CLI flags.
3. Generic flags, `--url site=URL` and `--skip site`.
4. Declarative per-site selector configs instead of scraper classes.

## Decision outcome

Chosen option: 1, a registry with generated flags.

`puxa_apto/sites.py` defines `Site` and `SITES`, a dict from site key to `Site` in run order. Each entry holds the console label, the display name, the host, the scraper class, the URL builder from `search.py`, a short note on what the site needs, the help text of its URL flag and an optional short alias. Everything else is generated from it:

- `SiteName` (`Literal[tuple(SITES)]`) and `SiteUrls` (one `List[str]` field per key, built with `create_model`) in `settings.py`, so `sites`, `urls.<key>` and `PUXA_URLS__<KEY>` work for every entry.
- `--<key>-url` (plus the short alias) and `--skip-<key>`, added to `scrape`'s signature by `_with_site_flags` in `cli.py`, in the same positions as the old hand-written options.
- The run order, the skip message and the `info` list.
- `SITE_HOSTS`, `AGENCY_HOSTS` and the fixture maps in the tests.

Scrapers stay hand-written classes on `BaseScraper` or `AgencyScraper`.

Option 2 was rejected because every site would still need two Typer options written by hand. Option 3 was rejected because it breaks `-v`, `-c`, `-i`, `-z` and `--skip-<site>` in existing scripts. Option 4 was rejected because the sites differ too much. Coordinates come from JSON-LD on one site, a Next.js RSC payload on another and an inline `locations` array on a third, and pagination and detail pages differ as well. A config able to describe all of that would turn into a programming language.

## Consequences

- Adding a site takes a scraper, a `<key>_urls` builder in `search.py`, one `Site` entry and a fixture. The README section "Adding a site" lists the steps.
- `search.py` imports `settings` only under `TYPE_CHECKING`. The chain settings, then sites, then search would otherwise be an import cycle.
- `SiteName` is `Literal[tuple(SITES)]`, which static type checkers can't resolve. Pydantic validates it at runtime, so `sites: ["olx"]` is still rejected.
- The skip message is now per site: `Skipping CERTA: nothing to search (needs Porto Alegre neighborhoods and aluguel, or pass --certa-url)`.
