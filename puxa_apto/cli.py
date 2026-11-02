import inspect
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from . import search
from .config import setup_logging
from .settings import SearchSettings, load_settings
from .sites import SITES, resolve_urls
from .utils.fingerprint import drop_cross_posts, filter_new_apartments
from .utils.storage import append_to_csv, load_existing_apartments, save_new_apartments_csv, save_to_json
from .xlsx import (
    SheetOptions,
    XlsxExportError,
    append_listings_sheet,
    check_workbook,
    read_listings,
    sheet_title,
)

app = typer.Typer(help="Apartment scraper")
console = Console()
logger = logging.getLogger(__name__)

DEFAULT_CONFIG_FILE = Path("puxa-apto.json")


def _parse_place(value: str) -> dict:
    name, sep, coords = value.rpartition("=")
    try:
        if not sep or not name.strip():
            raise ValueError(value)
        lat, lon = (float(part) for part in coords.split(","))
    except ValueError as err:
        raise typer.BadParameter("expected NAME=LAT,LON, e.g. HCPA=-30.0387,-51.2066", param_hint="--place") from err
    return {"name": name.strip(), "lat": lat, "lon": lon}


def _save_csv(new_apartments: List[Dict], csv_file: Optional[str]) -> None:
    """Write this run's new listings: appended to `csv_file`, to a timestamped sibling when its
    columns differ, or to a timestamped CSV of their own when no `csv_file` is configured."""
    if not csv_file:
        console.print(f"Data saved to CSV: [green]{save_new_apartments_csv(new_apartments)}[/green]")
        return
    written = append_to_csv(new_apartments, csv_file)
    if written == csv_file:
        console.print(f"Data appended to CSV: [green]{written}[/green] ({len(new_apartments)} listings)")
    else:
        console.print(f"[yellow]{csv_file} has different columns; new listings saved to {written}[/yellow]")


def _place_labels(settings: Optional[SearchSettings]) -> Dict[str, str]:
    """distance_km_<slug> key -> place name, labelling the sheet's distance columns."""
    return {search.distance_column(p): p.name for p in settings.places} if settings else {}


def _save_outputs(new_apartments: List[Dict], settings: SearchSettings) -> None:
    """Save this run's new listings. The Excel sheet goes first: if it fails, nothing is saved,
    so the listings aren't recorded as seen in the JSON history and a rerun retries them."""
    if settings.xlsx_file:
        options = SheetOptions(sheet_title(settings), _place_labels(settings), datetime.now().strftime("%d-%m"))
        try:
            sheet = append_listings_sheet(Path(settings.xlsx_file), new_apartments, options)
        except (XlsxExportError, OSError) as e:
            console.print(f"[red]Excel export failed: {e}. Nothing was saved; rerun to retry.[/red]")
            raise typer.Exit(code=1) from e
        console.print(
            f'Sheet "{sheet}" added to [green]{settings.xlsx_file}[/green] ({len(new_apartments)} listings)'
        )
    save_to_json(new_apartments, settings.json_file)
    console.print(f"Data saved to JSON: [green]{settings.json_file}[/green]")
    # --xlsx replaces the default timestamped CSV; an explicit --csv still gets written.
    if settings.csv_file or not settings.xlsx_file:
        _save_csv(new_apartments, settings.csv_file)


def _with_site_flags(command):
    """Give `command` --<key>-url (plus the site's short alias) and --skip-<key> per site, placed
    where the hand-written ones were; they arrive in **site_flags as <key>_url and skip_<key>."""
    signature = inspect.signature(command)
    params = [p for p in signature.parameters.values() if p.kind is not p.VAR_KEYWORD]
    at = [p.name for p in params].index("json_file")
    kind = inspect.Parameter.POSITIONAL_OR_KEYWORD
    urls = [
        inspect.Parameter(
            f"{key}_url",
            kind,
            annotation=Optional[List[str]],
            default=typer.Option(None, f"--{key}-url", *filter(None, [site.short_flag]), help=site.url_help),
        )
        for key, site in SITES.items()
    ]
    skips = [
        inspect.Parameter(
            f"skip_{key}",
            kind,
            annotation=bool,
            default=typer.Option(False, f"--skip-{key}", help=f"Skip {site.name} scraping"),
        )
        for key, site in SITES.items()
    ]
    command.__signature__ = signature.replace(parameters=params[:at] + urls + params[at:] + skips)
    return command



@app.command()
@_with_site_flags
def scrape(  # sensors: function-lines=124, complexity=24, params=15, statements=42 -- baseline: predates sensors; lower via refactor-tick
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-C",
        envvar="PUXA_CONFIG",
        help="Search config JSON (default: ./puxa-apto.json if present). See buscas/*.json",
    ),
    transaction: Optional[str] = typer.Option(
        None, "--transaction", "-t", help="aluguel or venda"
    ),
    place: Optional[List[str]] = typer.Option(
        None,
        "--place",
        help="Reference point NAME=LAT,LON, e.g. HCPA=-30.0387,-51.2066 (repeatable; replaces the config's places)",
    ),
    radius_km: Optional[float] = typer.Option(
        None, "--radius-km", "-r", help="Keep listings within this many km of any place"
    ),
    neighborhood: Optional[List[str]] = typer.Option(
        None, "--neighborhood", "-b", help="Neighborhood for Chaves/ImovelWeb (repeatable)"
    ),
    exclude_neighborhood: Optional[List[str]] = typer.Option(
        None, "--exclude-neighborhood", "-x", help="Drop listings in this neighborhood (repeatable)"
    ),
    max_price: Optional[float] = typer.Option(None, "--max-price", "-p", help="Maximum price"),
    max_total: Optional[float] = typer.Option(None, "--max-total", "-T", help="Maximum rent + condo fee"),
    min_area: Optional[int] = typer.Option(None, "--min-area", "-a", help="Minimum area in m²"),
    bedrooms: Optional[List[int]] = typer.Option(
        None, "--bedrooms", "-q", help="Accepted bedroom count (repeatable)"
    ),
    json_file: Optional[str] = typer.Option(
        None, "--json", "-j", help="Output JSON file path (default: apartamentos.json)"
    ),
    csv_file: Optional[str] = typer.Option(
        None,
        "--csv",
        help="CSV that each run appends its new listings to; never rewritten (default: a timestamped CSV of this run's new listings)",
    ),
    xlsx_file: Optional[str] = typer.Option(
        None, "--xlsx", help="Excel workbook each run adds a sheet of its new listings to (created if missing)"
    ),
    max_pages: Optional[int] = typer.Option(
        None, "--max-pages", "-m", help="Maximum number of pages to scrape per URL"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Enable verbose logging"),
    **site_flags,
):

    setup_logging(verbose=verbose)

    if config is not None and not config.is_file():
        console.print(f"[red]Config file not found: {config}[/red]")
        raise typer.Exit(code=2)
    config_file = config or (DEFAULT_CONFIG_FILE if DEFAULT_CONFIG_FILE.is_file() else None)

    flags = {
        "transaction": transaction,
        "places": [_parse_place(v) for v in place] if place else None,
        "radius_km": radius_km,
        "neighborhoods": neighborhood,
        "exclude_neighborhoods": exclude_neighborhood,
        "max_price": max_price,
        "max_total": max_total,
        "min_area": min_area,
        "bedrooms": bedrooms,
        "max_pages": max_pages,
        "json_file": json_file,
        "csv_file": csv_file,
        "xlsx_file": xlsx_file,
    }
    overrides = {k: v for k, v in flags.items() if v is not None and v != [] and v != ()}

    try:
        settings = load_settings(config_file, overrides)
    except ValidationError as e:
        console.print(f"[red]Invalid configuration:[/red]\n{e}")
        raise typer.Exit(code=2) from e
    if settings.xlsx_file:
        try:
            check_workbook(Path(settings.xlsx_file))
        except XlsxExportError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(code=2) from e

    site_urls = {
        key: resolve_urls(key, settings, list(site_flags[f"{key}_url"] or []))
        for key in SITES
        if key in settings.sites and not site_flags[f"skip_{key}"]
    }
    if not any(site_urls.values()):
        console.print(
            "[red]Nothing to search: configure places or neighborhoods (see buscas/*.json), "
            "or pass a site URL.[/red]"
        )
        raise typer.Exit(code=2)

    console.print("\n[bold blue]Apartment Scraper[/bold blue]\n")

    console.print("Loading existing apartments...")
    existing_links, existing_fingerprints, existing_refs = load_existing_apartments(
        settings.json_file, settings.csv_file or "apartamentos.csv"
    )
    console.print(
        f"Found [green]{len(existing_links)}[/green] unique links and "
        f"[green]{len(existing_fingerprints)}[/green] unique fingerprints already saved.\n"
    )

    all_apartments = _scrape_sites(site_urls, settings.max_pages)

    console.print(f"\n[bold]{'='*50}[/bold]")
    console.print(f"[bold]Total apartments found:[/bold] [green]{len(all_apartments)}[/green]")
    console.print(f"{'='*50}\n")

    # A ref is known once any of its copies was saved, even by a run that didn't record refs.
    existing_refs.update(
        a["agency_ref"] for a in all_apartments if a.get("agency_ref") and a["link"] in existing_links
    )
    found = len(all_apartments)
    all_apartments = drop_cross_posts(all_apartments)
    console.print(f"Cross-posted copies dropped: [yellow]{found - len(all_apartments)}[/yellow]")
    search.annotate(all_apartments, settings)
    matching = search.apply_criteria(all_apartments, settings)
    console.print(
        f"Matching criteria: [green]{len(matching)}[/green] "
        f"(dropped {len(all_apartments) - len(matching)})"
    )

    new_apartments = filter_new_apartments(matching, existing_links, existing_fingerprints, existing_refs)

    console.print(f"New apartments: [green]{len(new_apartments)}[/green]")
    console.print(f"Duplicates filtered: [yellow]{len(matching) - len(new_apartments)}[/yellow]\n")

    if new_apartments:
        _save_outputs(new_apartments, settings)
        _print_preview(new_apartments)
    else:
        console.print("[yellow]No new apartments found.[/yellow]")


def _scrape_sites(site_urls: Dict[str, List[str]], max_pages: Optional[int]) -> List[Dict]:
    """Every listing the sites' scrapers return for their URLs; a failing URL is logged and skipped."""
    all_apartments: List[Dict] = []
    for key, urls in site_urls.items():
        site = SITES[key]
        if not urls:
            console.print(
                f"[yellow]Skipping {site.label}: nothing to search (needs {site.needs}, or pass --{key}-url)[/yellow]\n"
            )
            continue

        console.print(f"[bold cyan]{site.label}[/bold cyan]")
        console.print("=" * 50)
        for url in urls:
            try:
                apartments = site.scraper(url).scrape(max_pages=max_pages)
                all_apartments.extend(apartments)
                console.print(f"Found [green]{len(apartments)}[/green] apartments\n")
            except Exception as e:
                logger.error(f"Error scraping {site.label}: {e}")
                console.print(f"[red]Error scraping {site.label}: {e}[/red]\n")
    return all_apartments


def _money(value) -> str:
    return f"R$ {value:,.2f}" if value else "N/A"


def _print_preview(new_apartments: List[Dict]) -> None:
    """One table per listing for the first three new ones."""
    console.print("\n[bold]--- First 3 new apartments ---[/bold]")
    for i, apt in enumerate(new_apartments[:3], 1):
        table = Table(title=f"Apartment {i}", show_header=True, header_style="bold magenta")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Street", apt.get("street", "N/A"))
        table.add_row("Neighborhood", apt.get("neighborhood", "N/A"))
        table.add_row("City", apt.get("city", "N/A"))
        table.add_row("Area", f"{apt.get('area', 'N/A')} m²")
        table.add_row("Bedrooms", str(apt.get("bedrooms", "N/A")))
        table.add_row("Bathrooms", str(apt.get("bathrooms", "N/A")))
        table.add_row("Parking", str(apt.get("parking", "N/A")))
        table.add_row("Price", _money(apt.get("price")))
        table.add_row("Condo Fee", _money(apt.get("condo_fee")))
        table.add_row("IPTU", _money(apt.get("iptu")))
        table.add_row("Link", apt.get("link", "N/A"))

        console.print(table)
        console.print()


@app.command("export-xlsx")
def export_xlsx(
    source: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="Listings file: a JSON history (json_file) or a CSV written by scrape"
    ),
    output: Path = typer.Option(..., "--output", "-o", help="Workbook to create, or to add a sheet to"),
    config: Optional[Path] = typer.Option(
        None, "--config", "-C", exists=True, dir_okay=False, help="Search config whose title and places label the sheet"
    ),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="Sheet name (default: the source file's date, DD-MM)"
    ),
):
    """Add a sheet of already saved listings to an Excel workbook."""
    setup_logging(verbose=False)
    try:
        settings = load_settings(config, {}) if config else None
    except ValidationError as e:
        console.print(f"[red]Invalid configuration:[/red]\n{e}")
        raise typer.Exit(code=2) from e
    try:
        listings = read_listings(source)
        if not listings:
            console.print(f"[red]No listings in {source}[/red]")
            raise typer.Exit(code=1)
        sheet_name = name or datetime.fromtimestamp(source.stat().st_mtime).strftime("%d-%m")
        options = SheetOptions(sheet_title(settings), _place_labels(settings), sheet_name)
        sheet = append_listings_sheet(output, listings, options)
    except XlsxExportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=2) from e
    console.print(f'Sheet "{sheet}" added to [green]{output}[/green] ({len(listings)} listings)')


@app.command()
def info():
    console.print("[bold blue]Puxa Apto - Apartment Scraper[/bold blue]\n")
    console.print("A CLI tool for scraping apartment listings from Brazilian real estate websites.")
    console.print("\nSupported websites:")
    for site in SITES.values():
        console.print(f"  • {site.name} ({site.host})")
    console.print("\nUse [cyan]puxa-apto scrape --help[/cyan] for usage information.")


if __name__ == "__main__":
    app()