import json
import logging
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from typer.testing import CliRunner

from puxa_apto.cli import app
from puxa_apto.search import slugify

BUSCAS = Path(__file__).resolve().parents[1] / "buscas"
FAMED = str(BUSCAS / "famed-ufrgs.json")
FAMED_VIEWPORT = "viewport=-51.1951%2C-30.0292%7C-51.2201%2C-30.0508"
SITE_HOSTS = ("vivareal.com.br", "zapimoveis.com.br", "chavesnamao.com.br", "imovelweb.com.br")


def run(*args):
    # setup_logging binds a handler to the previous run's captured stdout; start each run clean.
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    result = CliRunner().invoke(app, ["scrape", *args])
    assert result.exit_code == 0, result.output
    return result


def scrape_into(tmp_path, name, *args):
    out = tmp_path / f"{name}.json"
    run(*args, "--json", str(out), "--csv", str(tmp_path / f"{name}.csv"))
    return json.loads(out.read_text(encoding="utf-8")) if out.exists() else []


def vivareal_searches(requested):
    return [url for url in requested if "vivareal.com.br" in url]


def famed_copy(tmp_path, **changes):
    config = json.loads((BUSCAS / "famed-ufrgs.json").read_text(encoding="utf-8"))
    config.update(changes)
    path = tmp_path / "busca.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return str(path)


def is_centro_historico(apt):
    return slugify(apt.get("neighborhood") or "") == "centro-historico"


def test_configured_search_returns_usable_listings_from_all_sites(fake_sites, tmp_path):
    saved = scrape_into(tmp_path, "out", "-C", FAMED, "-m", "1")

    by_site = defaultdict(list)
    for apt in saved:
        host = urlparse(apt["link"]).netloc
        site = next(h for h in SITE_HOSTS if host.endswith(h))
        by_site[site].append(apt)
    assert set(by_site) == set(SITE_HOSTS)

    for site, apts in by_site.items():
        complete = [
            a
            for a in apts
            if a["price"] is not None
            and a["area"] is not None
            and a["bedrooms"] is not None
            and a["neighborhood"]
        ]
        assert len(complete) >= 0.8 * len(apts), site

    assert any(a["condo_fee"] for a in by_site["vivareal.com.br"])
    assert any(a["condo_fee"] for a in by_site["imovelweb.com.br"])
    assert not any("?" in a["link"] for a in by_site["imovelweb.com.br"])

    (search,) = vivareal_searches(fake_sites)
    assert "transacao=aluguel" in search
    assert FAMED_VIEWPORT in search


def test_filter_flags_narrow_the_results(fake_sites, tmp_path):
    unfiltered = scrape_into(tmp_path, "all", "-C", FAMED, "-m", "1")
    assert any((a["price"] or 0) > 3000 or (a["bedrooms"] or 0) >= 3 for a in unfiltered)

    fake_sites.clear()
    filtered = scrape_into(
        tmp_path, "filtered", "-C", FAMED, "-m", "1", "--max-price", "3000", "-q", "1", "-q", "2"
    )

    assert filtered
    assert all(a["price"] <= 3000 for a in filtered if a["price"] is not None)
    assert all(a["bedrooms"] in (1, 2) for a in filtered if a["bedrooms"] is not None)
    (search,) = vivareal_searches(fake_sites)
    assert "precoMaximo=3000" in search
    assert "quartos=1%2C2" in search


def test_flags_beat_env_vars_which_beat_the_config_file(fake_sites, tmp_path, monkeypatch):
    config = tmp_path / "busca.json"
    config.write_text(
        json.dumps({"transaction": "aluguel", "center": {"lat": -30.04, "lon": -51.2076}, "max_price": 5000}),
        encoding="utf-8",
    )
    monkeypatch.setenv("PUXA_MAX_PRICE", "2000")

    scrape_into(tmp_path, "env", "-C", str(config), "-m", "1")
    (search,) = vivareal_searches(fake_sites)
    assert "precoMaximo=2000" in search

    fake_sites.clear()
    scrape_into(tmp_path, "flag", "-C", str(config), "-m", "1", "--max-price", "2500")
    (search,) = vivareal_searches(fake_sites)
    assert "precoMaximo=2500" in search


def test_excluded_neighborhoods_never_appear_regardless_of_accents_or_case(fake_sites, tmp_path):
    unexcluded = famed_copy(tmp_path, exclude_neighborhoods=[])

    assert any(is_centro_historico(a) for a in scrape_into(tmp_path, "all", "-C", unexcluded, "-m", "1"))
    assert not any(is_centro_historico(a) for a in scrape_into(tmp_path, "famed", "-C", FAMED, "-m", "1"))
    flagged = scrape_into(tmp_path, "flag", "-C", unexcluded, "-m", "1", "-x", "centro historico")
    assert not any(is_centro_historico(a) for a in flagged)


def test_rerunning_the_same_search_reports_nothing_new(fake_sites, tmp_path):
    out = tmp_path / "out.json"
    args = ["-C", FAMED, "-m", "1", "--json", str(out), "--csv", str(tmp_path / "out.csv")]

    run(*args)
    first = json.loads(out.read_text(encoding="utf-8"))
    second_run = run(*args)

    assert "New apartments: 0" in second_run.output
    assert len(json.loads(out.read_text(encoding="utf-8"))) == len(first)
