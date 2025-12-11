import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import (
    DEFAULT_CHAVES_URL,
    DEFAULT_IMOVELWEB_URL,
    DEFAULT_JSON_FILE,
    DEFAULT_VIVAREAL_URL,
    DEFAULT_ZAP_URL,
    setup_logging,
)
from .scrapers import ChavesScraper, ImovelWebScraper, VivaRealScraper, ZapScraper
from .utils.fingerprint import filter_new_apartments
from .utils.storage import load_existing_apartments, save_new_apartments_csv, save_to_json

app = typer.Typer(help="Apartment scraper")
console = Console()
logger = logging.getLogger(__name__)


@app.command()
def scrape(
    vivareal_url: Optional[str] = typer.Option(
        DEFAULT_VIVAREAL_URL, "--vivareal-url", "-v", help="VivaReal search URL"
    ),
    chaves_url: Optional[str] = typer.Option(
        DEFAULT_CHAVES_URL, "--chaves-url", "-c", help="Chaves na Mão search URL"
    ),
    imovelweb_url: Optional[str] = typer.Option(
        DEFAULT_IMOVELWEB_URL, "--imovelweb-url", "-i", help="ImovelWeb search URL"
    ),
    zap_url: Optional[str] = typer.Option(
        DEFAULT_ZAP_URL, "--zap-url", "-z", help="Zap Imóveis search URL"
    ),
    json_file: str = typer.Option(
        DEFAULT_JSON_FILE, "--json", "-j", help="Output JSON file path"
    ),
    csv_file: Optional[str] = typer.Option(
        None, "--csv", help="Output CSV file path (default: timestamped)"
    ),
    max_pages: Optional[int] = typer.Option(
        None, "--max-pages", "-m", help="Maximum number of pages to scrape per site"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Enable verbose logging"),
    skip_vivareal: bool = typer.Option(False, "--skip-vivareal", help="Skip VivaReal scraping"),
    skip_chaves: bool = typer.Option(False, "--skip-chaves", help="Skip Chaves na Mão scraping"),
    skip_imovelweb: bool = typer.Option(False, "--skip-imovelweb", help="Skip ImovelWeb scraping"),
    skip_zap: bool = typer.Option(False, "--skip-zap", help="Skip Zap Imóveis scraping"),
):

    setup_logging(verbose=verbose)

    console.print("\n[bold blue]Apartment Scraper[/bold blue]\n")

    console.print("Loading existing apartments...")
    existing_links, existing_fingerprints = load_existing_apartments(json_file, csv_file or "apartamentos.csv")
    console.print(
        f"Found [green]{len(existing_links)}[/green] unique links and "
        f"[green]{len(existing_fingerprints)}[/green] unique fingerprints already saved.\n"
    )

    all_apartments = []

    if not skip_vivareal:
        console.print("[bold cyan]VIVAREAL[/bold cyan]")
        console.print("=" * 50)
        try:
            scraper = VivaRealScraper(vivareal_url)
            apartments_vivareal = scraper.scrape(max_pages=max_pages)
            all_apartments.extend(apartments_vivareal)
            console.print(f"Found [green]{len(apartments_vivareal)}[/green] apartments\n")
        except Exception as e:
            logger.error(f"Error scraping VivaReal: {e}")
            console.print(f"[red]Error scraping VivaReal: {e}[/red]\n")

    if not skip_chaves:
        console.print("[bold cyan]CHAVES NA MÃO[/bold cyan]")
        console.print("=" * 50)
        try:
            scraper = ChavesScraper(chaves_url)
            apartments_chaves = scraper.scrape(max_pages=max_pages)
            all_apartments.extend(apartments_chaves)
            console.print(f"Found [green]{len(apartments_chaves)}[/green] apartments\n")
        except Exception as e:
            logger.error(f"Error scraping Chaves na Mão: {e}")
            console.print(f"[red]Error scraping Chaves na Mão: {e}[/red]\n")

    if not skip_imovelweb:
        console.print("[bold cyan]IMOVELWEB[/bold cyan]")
        console.print("=" * 50)
        try:
            scraper = ImovelWebScraper(imovelweb_url)
            apartments_imovelweb = scraper.scrape(max_pages=max_pages)
            all_apartments.extend(apartments_imovelweb)
            console.print(f"Found [green]{len(apartments_imovelweb)}[/green] apartments\n")
        except Exception as e:
            logger.error(f"Error scraping ImovelWeb: {e}")
            console.print(f"[red]Error scraping ImovelWeb: {e}[/red]\n")

    if not skip_zap:
        console.print("[bold cyan]ZAP IMÓVEIS[/bold cyan]")
        console.print("=" * 50)
        try:
            scraper = ZapScraper(zap_url)
            apartments_zap = scraper.scrape(max_pages=max_pages)
            all_apartments.extend(apartments_zap)
            console.print(f"Found [green]{len(apartments_zap)}[/green] apartments\n")
        except Exception as e:
            logger.error(f"Error scraping Zap Imóveis: {e}")
            console.print(f"[red]Error scraping Zap Imóveis: {e}[/red]\n")

    console.print(f"\n[bold]{'='*50}[/bold]")
    console.print(f"[bold]Total apartments found:[/bold] [green]{len(all_apartments)}[/green]")
    console.print(f"{'='*50}\n")

    new_apartments = filter_new_apartments(all_apartments, existing_links, existing_fingerprints)

    console.print(f"New apartments: [green]{len(new_apartments)}[/green]")
    console.print(f"Duplicates filtered: [yellow]{len(all_apartments) - len(new_apartments)}[/yellow]\n")

    if new_apartments:
        save_to_json(new_apartments, json_file)
        console.print(f"Data saved to JSON: [green]{json_file}[/green]")

        if csv_file:
            from .utils.storage import save_to_csv
            save_to_csv(new_apartments, csv_file)
            console.print(f"Data saved to CSV: [green]{csv_file}[/green]")
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
    console.print("\nUse [cyan]puxa-apto scrape --help[/cyan] for usage information.")


if __name__ == "__main__":
    app()