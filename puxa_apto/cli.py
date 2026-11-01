import logging
from pathlib import Path
from typing import List, Optional

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from . import search
from .config import setup_logging
from .scrapers import (
    CertaScraper,
    ChavesScraper,
    ImovelWebScraper,
    LeindeckerScraper,
    VivaRealScraper,
    ZapScraper,
)
from .settings import load_settings
from .utils.fingerprint import drop_cross_posts, filter_new_apartments
from .utils.storage import load_existing_apartments, save_new_apartments_csv, save_to_csv, save_to_json

app = typer.Typer(help="Apartment scraper")
console = Console()
logger = logging.getLogger(__name__)

DEFAULT_CONFIG_FILE = Path("puxa-apto.json")

SCRAPERS = {
    "vivareal": ("VIVAREAL", VivaRealScraper),
    "chaves": ("CHAVES NA MÃO", ChavesScraper),
    "imovelweb": ("IMOVELWEB", ImovelWebScraper),
    "zap": ("ZAP IMÓVEIS", ZapScraper),
    "leindecker": ("LEINDECKER", LeindeckerScraper),
    "certa": ("CERTA", CertaScraper),
}


def _parse_place(value: str) -> dict:
    name, sep, coords = value.rpartition("=")
    try:
        if not sep or not name.strip():
            raise ValueError(value)
        lat, lon = (float(part) for part in coords.split(","))
    except ValueError:
        raise typer.BadParameter("expected NAME=LAT,LON, e.g. HCPA=-30.0387,-51.2066", param_hint="--place")
    return {"name": name.strip(), "lat": lat, "lon": lon}


@app.command()
def scrape(
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
    vivareal_url: Optional[List[str]] = typer.Option(
        None, "--vivareal-url", "-v", help="VivaReal search URL (repeatable; replaces the built one)"
    ),
    chaves_url: Optional[List[str]] = typer.Option(
        None, "--chaves-url", "-c", help="Chaves na Mão search URL (repeatable; replaces the built ones)"
    ),
    imovelweb_url: Optional[List[str]] = typer.Option(
        None, "--imovelweb-url", "-i", help="ImovelWeb search URL (repeatable; replaces the built one)"
    ),
    zap_url: Optional[List[str]] = typer.Option(
        None, "--zap-url", "-z", help="Zap Imóveis search URL (repeatable; replaces the built one)"
    ),
    leindecker_url: Optional[List[str]] = typer.Option(
        None,
        "--leindecker-url",
        help="Leindecker search URL ending with its page number, e.g. …/1/ (repeatable; replaces the built one)",
    ),
    certa_url: Optional[List[str]] = typer.Option(
        None,
        "--certa-url",
        help="Certa search URL ending with its page number, e.g. …/1/ (repeatable; replaces the built one)",
    ),
    json_file: Optional[str] = typer.Option(
        None, "--json", "-j", help="Output JSON file path (default: apartamentos.json)"
    ),
    csv_file: Optional[str] = typer.Option(
        None,
        "--csv",
        help="CSV mirror of the whole JSON file, rewritten each run (default: a timestamped CSV of this run's new listings)",
    ),
    max_pages: Optional[int] = typer.Option(
        None, "--max-pages", "-m", help="Maximum number of pages to scrape per URL"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Enable verbose logging"),
    skip_vivareal: bool = typer.Option(False, "--skip-vivareal", help="Skip VivaReal scraping"),
    skip_chaves: bool = typer.Option(False, "--skip-chaves", help="Skip Chaves na Mão scraping"),
    skip_imovelweb: bool = typer.Option(False, "--skip-imovelweb", help="Skip ImovelWeb scraping"),
    skip_zap: bool = typer.Option(False, "--skip-zap", help="Skip Zap Imóveis scraping"),
    skip_leindecker: bool = typer.Option(False, "--skip-leindecker", help="Skip Leindecker scraping"),
    skip_certa: bool = typer.Option(False, "--skip-certa", help="Skip Certa scraping"),
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
    }
    overrides = {k: v for k, v in flags.items() if v is not None and v != [] and v != ()}

    try:
        settings = load_settings(config_file, overrides)
    except ValidationError as e:
        console.print(f"[red]Invalid configuration:[/red]\n{e}")
        raise typer.Exit(code=2)

    cli_urls = {
        "vivareal": vivareal_url,
        "chaves": chaves_url,
        "imovelweb": imovelweb_url,
        "zap": zap_url,
        "leindecker": leindecker_url,
        "certa": certa_url,
    }
    skipped = {
        "vivareal": skip_vivareal,
        "chaves": skip_chaves,
        "imovelweb": skip_imovelweb,
        "zap": skip_zap,
        "leindecker": skip_leindecker,
        "certa": skip_certa,
    }
    site_urls = {
        site: search.resolve_urls(site, settings, list(cli_urls[site] or []))
        for site in search.SITES
        if site in settings.sites and not skipped[site]
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

    all_apartments = []

    for site, urls in site_urls.items():
        label, scraper_cls = SCRAPERS[site]
        if not urls:
            console.print(
                f"[yellow]Skipping {label}: nothing to search (set places for VivaReal/Zap, "
                "neighborhoods for Chaves/ImovelWeb, Porto Alegre neighborhoods for "
                "Leindecker/Certa (Certa: aluguel only), or pass a URL)[/yellow]\n"
            )
            continue

        console.print(f"[bold cyan]{label}[/bold cyan]")
        console.print("=" * 50)
        for url in urls:
            try:
                apartments = scraper_cls(url).scrape(max_pages=settings.max_pages)
                all_apartments.extend(apartments)
                console.print(f"Found [green]{len(apartments)}[/green] apartments\n")
            except Exception as e:
                logger.error(f"Error scraping {label}: {e}")
                console.print(f"[red]Error scraping {label}: {e}[/red]\n")

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
        saved = save_to_json(new_apartments, settings.json_file)
        console.print(f"Data saved to JSON: [green]{settings.json_file}[/green]")

        if settings.csv_file:
            save_to_csv(saved, settings.csv_file)
            console.print(f"Data saved to CSV: [green]{settings.csv_file}[/green] ({len(saved)} listings)")
        else:
            csv_filename = save_new_apartments_csv(new_apartments)
            if csv_filename:
                console.print(f"Data saved to CSV: [green]{csv_filename}[/green]")

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
            table.add_row(
                "Price",
                f"R$ {apt.get('price', 0):,.2f}" if apt.get("price") else "N/A",
            )
            table.add_row(
                "Condo Fee",
                f"R$ {apt.get('condo_fee', 0):,.2f}" if apt.get("condo_fee") else "N/A",
            )
            table.add_row(
                "IPTU",
                f"R$ {apt.get('iptu', 0):,.2f}" if apt.get("iptu") else "N/A",
            )
            table.add_row("Link", apt.get("link", "N/A"))

            console.print(table)
            console.print()
    else:
        console.print("[yellow]No new apartments found.[/yellow]")


@app.command()
def info():
    console.print("[bold blue]Puxa Apto - Apartment Scraper[/bold blue]\n")
    console.print("A CLI tool for scraping apartment listings from Brazilian real estate websites.")
    console.print("\nSupported websites:")
    console.print("  • VivaReal (vivareal.com.br)")
    console.print("  • Chaves na Mão (chavesnamao.com.br)")
    console.print("  • ImovelWeb (imovelweb.com.br)")
    console.print("  • Zap Imóveis (zapimoveis.com.br)")
    console.print("  • Leindecker (leindecker.com.br)")
    console.print("  • Certa (certa.com.br)")
    console.print("\nUse [cyan]puxa-apto scrape --help[/cyan] for usage information.")


if __name__ == "__main__":
    app()