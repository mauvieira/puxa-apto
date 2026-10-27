import csv
import json
import logging
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from typer.testing import CliRunner

from puxa_apto.cli import app
from puxa_apto.utils.text import slugify

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FAMED = str(FIXTURES / "famed.json")
FAMED_VIEWPORT = "viewport=-51.1941%2C-30.0262%7C-51.2223%2C-30.0511"
FAMED_PLACE_COLUMNS = ("distance_km_famed", "distance_km_hcpa", "distance_km_hps", "distance_km_campus_saude")
SITE_HOSTS = (
    "vivareal.com.br",
    "zapimoveis.com.br",
    "chavesnamao.com.br",
    "imovelweb.com.br",
    "leindecker.com.br",
    "certa.com.br",
)
AGENCY_HOSTS = ("leindecker.com.br", "certa.com.br")
FAMED_LEINDECKER = (
    "https://www.leindecker.com.br/busca/alugar/cidade/porto-alegre/bairros/"
    "santa-cecilia_rio-branco_bom-fim_santana_farroupilha_independencia_moinhos-de-vento_jardim-botanico"
    "/categorias/apartamentos_jk-lofts_studios/1/"
)
FAMED_CERTA = (
    "https://www.certa.com.br/busca/alugar/categorias/apartamentos_kitnet-jk_studios/bairros/"
    "santa-cecilia-porto-alegre_rio-branco-porto-alegre_bom-fim-porto-alegre_santana-porto-alegre_"
    "farroupilha-porto-alegre_independencia-porto-alegre_moinhos-de-vento-porto-alegre_"
    "jardim-botanico-porto-alegre/1/"
)


def invoke(*args):
    # setup_logging binds a handler to the previous run's captured stdout; start each run clean.
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    return CliRunner().invoke(app, ["scrape", *args])


def run(*args):
    result = invoke(*args)
    assert result.exit_code == 0, result.output
    return result


def scrape_into(tmp_path, name, *args):
    out = tmp_path / f"{name}.json"
    run(*args, "--json", str(out), "--csv", str(tmp_path / f"{name}.csv"))
    return json.loads(out.read_text(encoding="utf-8")) if out.exists() else []


def csv_header(tmp_path, name):
    return (tmp_path / f"{name}.csv").read_text(encoding="utf-8").splitlines()[0].split(",")


def vivareal_searches(requested):
    return [url for url in requested if "vivareal.com.br" in url]


def famed_copy(tmp_path, **changes):
    config = json.loads((FIXTURES / "famed.json").read_text(encoding="utf-8"))
    config.update(changes)
    path = tmp_path / "busca.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return str(path)


def is_centro_historico(apt):
    return slugify(apt.get("neighborhood") or "") == "centro-historico"


def site_of(apt):
    host = urlparse(apt["link"]).netloc
    return next(h for h in SITE_HOSTS if host.endswith(h))


def agency_searches(requested, host):
    return [url for url in requested if host in url and "/busca/" in url]


def test_configured_search_returns_usable_listings_from_all_sites(fake_sites, tmp_path):
    saved = scrape_into(tmp_path, "out", "-C", FAMED, "-m", "1")

    by_site = defaultdict(list)
    for apt in saved:
        by_site[site_of(apt)].append(apt)
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
        json.dumps(
            {
                "transaction": "aluguel",
                "places": [{"name": "Famed", "lat": -30.04, "lon": -51.2076}],
                "max_price": 5000,
            }
        ),
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


def test_distances_to_every_reference_point_are_saved_and_the_radius_applies(fake_sites, tmp_path):
    wide = scrape_into(tmp_path, "wide", "-C", FAMED, "-m", "1", "-r", "50")
    assert any((a["distance_km"] or 0) > 1.2 for a in wide)

    saved = scrape_into(tmp_path, "out", "-C", FAMED, "-m", "1")

    assert saved
    for apt in saved:
        assert {"distance_km", *FAMED_PLACE_COLUMNS} <= apt.keys()
        # With places set, a listing whose distance can't be computed isn't known to be near.
        assert apt["distance_km"] is not None, apt["link"]
        assert apt["distance_km"] == min(apt[c] for c in FAMED_PLACE_COLUMNS)
        assert apt["distance_km"] <= 1.2
    assert {site_of(a) for a in saved} == set(SITE_HOSTS)
    assert {"distance_km", "distance_km_hps", "description"} <= set(csv_header(tmp_path, "out"))


def test_place_flag_replaces_the_configured_points(fake_sites, tmp_path):
    saved = scrape_into(tmp_path, "out", "-C", FAMED, "-m", "1", "--place", "HPS=-30.0369333,-51.2098087")

    assert saved
    assert all("distance_km_hps" in a and "distance_km_famed" not in a for a in saved)

    malformed = invoke("-C", FAMED, "--place", "abc")
    assert malformed.exit_code == 2
    assert "expected NAME=LAT,LON" in malformed.output

    twin = {"name": "HCPA", "lat": -30.0387, "lon": -51.2066}
    duplicated = invoke("-C", famed_copy(tmp_path, places=[twin, twin]))
    assert duplicated.exit_code == 2
    assert "Invalid configuration" in duplicated.output
    assert "place names must be unique" in duplicated.output


def test_max_total_caps_rent_plus_condo_and_reaches_every_site_search(fake_sites, tmp_path):
    uncapped = scrape_into(tmp_path, "all", "-C", FAMED, "-m", "1")
    assert any(a["price"] is not None and a["price"] <= 1800 < a["total_price"] for a in uncapped)

    fake_sites.clear()
    capped = scrape_into(tmp_path, "capped", "-C", FAMED, "-m", "1", "--max-total", "1800")

    assert capped
    for apt in capped:
        if apt["price"] is not None:
            assert apt["total_price"] == apt["price"] + (apt["condo_fee"] or 0)
            assert apt["total_price"] <= 1800
    (search,) = vivareal_searches(fake_sites)
    assert "precoMaximo=1800" in search
    assert any("chavesnamao.com.br" in url and "filtro=pmax%3A1800" in url for url in fake_sites)
    assert any("imovelweb.com.br" in url and url.endswith("-menos-1800-reales.html") for url in fake_sites)
    assert "total_price" in csv_header(tmp_path, "capped")



def test_descriptions_and_amenity_codes_are_saved(fake_sites, tmp_path):
    saved = scrape_into(tmp_path, "out", "-C", FAMED, "-m", "1")

    imovelweb = [a for a in saved if site_of(a) == "imovelweb.com.br"]
    assert imovelweb
    assert sum(1 for a in imovelweb if a["description"]) >= 0.8 * len(imovelweb)
    assert any(a["amenity_codes"] for a in saved if site_of(a) == "zapimoveis.com.br")
    assert all(isinstance(a["description"], str) for a in saved)
    assert all(isinstance(a["amenity_codes"], list) for a in saved)


def test_porto_alegre_search_returns_agency_listings_with_coordinates_condo_and_details(
    fake_sites, tmp_path
):
    saved = scrape_into(tmp_path, "out", "-C", FAMED, "-m", "1", "-r", "50")

    for host in AGENCY_HOSTS:
        apts = [a for a in saved if site_of(a) == host]
        assert apts, host
        detailed = [
            a
            for a in apts
            if a["street"] and a["description"] and a["amenity_codes"] and (a["condo_fee"] or 0) > 0
        ]
        assert len(detailed) >= 0.8 * len(apts), host
        for apt in apts:
            if apt["price"] is not None:
                assert apt["total_price"] == apt["price"] + (apt["condo_fee"] or 0)
            assert re.fullmatch(r"(leindecker|certa):\d+", apt["agency_ref"])
    assert FAMED_LEINDECKER in fake_sites
    assert FAMED_CERTA in fake_sites
    assert "agency_ref" in csv_header(tmp_path, "out")

    fake_sites.clear()
    scrape_into(
        tmp_path, "filtered", "-C", FAMED, "-m", "1", "--max-total", "1800", "--min-area", "40", "-q", "2", "-q", "3"
    )
    assert any(
        u.endswith("/valor_ate/1800/area/40/dormitorios/2/1/") for u in agency_searches(fake_sites, "leindecker")
    )
    assert any(u.endswith("/valor_ate/1800/area/40/quartos/2/1/") for u in agency_searches(fake_sites, "certa"))


def test_config_chooses_the_sites_and_agencies_run_only_for_porto_alegre(fake_sites, tmp_path):
    only_certa = scrape_into(tmp_path, "certa", "-C", famed_copy(tmp_path, sites=["certa"]), "-m", "1")
    assert only_certa
    assert all("certa.com.br" in url for url in fake_sites)
    assert all(site_of(a) == "certa.com.br" for a in only_certa)

    fake_sites.clear()
    curitiba = run("-C", famed_copy(tmp_path, city="Curitiba", state="PR"), "-m", "1")
    assert not any(host in url for url in fake_sites for host in AGENCY_HOSTS)
    assert "Skipping LEINDECKER" in curitiba.output
    assert "Skipping CERTA" in curitiba.output

    fake_sites.clear()
    run("-C", famed_copy(tmp_path, transaction="venda"), "-m", "1")
    (leindecker,) = agency_searches(fake_sites, "leindecker")
    assert leindecker.startswith("https://www.leindecker.com.br/busca/comprar/")
    assert "categorias/apartamentos_jk-loft-kitnet/" in leindecker
    assert not agency_searches(fake_sites, "certa")

    unknown = invoke("-C", famed_copy(tmp_path, sites=["olx"]))
    assert unknown.exit_code == 2
    assert "Invalid configuration" in unknown.output

    fake_sites.clear()
    run("-C", FAMED, "-m", "1", "--skip-leindecker")
    assert not agency_searches(fake_sites, "leindecker")


def test_a_listing_cross_posted_on_the_portals_is_saved_once_as_the_agency_copy(fake_sites, tmp_path):
    portals = scrape_into(
        tmp_path, "portals", "-C", FAMED, "-m", "1", "-r", "50", "--skip-leindecker", "--skip-certa"
    )
    portal_copies = {a["agency_ref"]: a for a in portals if a["agency_ref"]}
    assert portal_copies

    saved = scrape_into(tmp_path, "all", "-C", FAMED, "-m", "1", "-r", "50")

    refs = [a["agency_ref"] for a in saved if a["agency_ref"]]
    assert len(refs) == len(set(refs))
    overlap = set(portal_copies) & {a["agency_ref"] for a in saved if site_of(a) in AGENCY_HOSTS}
    assert overlap
    for apt in saved:
        if apt["agency_ref"] in overlap:
            assert site_of(apt) in AGENCY_HOSTS
            # The agency's map can lag its newest listings; the portal copy's point fills the gap.
            if portal_copies[apt["agency_ref"]]["lat"] is not None:
                assert apt["lat"] is not None and apt["distance_km"] is not None


def test_a_listing_saved_earlier_from_a_portal_is_not_saved_again_from_the_agency(fake_sites, tmp_path):
    first = scrape_into(tmp_path, "a", "-C", FAMED, "-m", "1", "-r", "50")
    ref = next(a["agency_ref"] for a in first if site_of(a) == "leindecker.com.br")
    earlier = tmp_path / "b.json"
    earlier.write_text(
        json.dumps([{"link": "https://www.zapimoveis.com.br/imovel/x-id-1/", "agency_ref": ref}]),
        encoding="utf-8",
    )

    run("-C", FAMED, "-m", "1", "-r", "50", "--json", str(earlier), "--csv", str(tmp_path / "b.csv"))

    saved = json.loads(earlier.read_text(encoding="utf-8"))
    assert sum(1 for a in saved if a.get("agency_ref") == ref) == 1


def test_a_portal_copy_saved_before_agency_refs_existed_still_blocks_the_agency_copy(fake_sites, tmp_path):
    out = tmp_path / "out.json"
    args = ["-C", FAMED, "-m", "1", "-r", "50", "--json", str(out), "--csv", str(tmp_path / "out.csv")]
    run(*args, "--skip-leindecker", "--skip-certa")
    legacy = json.loads(out.read_text(encoding="utf-8"))
    portal_refs = {a.pop("agency_ref") for a in legacy} - {None}
    out.write_text(json.dumps(legacy), encoding="utf-8")
    (tmp_path / "out.csv").unlink()  # legacy CSVs have no agency_ref column

    run(*args)

    added = json.loads(out.read_text(encoding="utf-8"))[len(legacy):]
    assert added
    assert not portal_refs & {a["agency_ref"] for a in added}


def test_a_fixed_csv_keeps_every_listing_saved_across_runs(fake_sites, tmp_path):
    first = scrape_into(tmp_path, "out", "-C", FAMED, "-m", "1", "-r", "50", "--skip-zap")
    saved = scrape_into(tmp_path, "out", "-C", FAMED, "-m", "1", "-r", "50")

    assert len(saved) > len(first)
    with open(tmp_path / "out.csv", newline="", encoding="utf-8") as f:
        csv_links = [row["link"] for row in csv.DictReader(f)]
    assert csv_links == [a["link"] for a in saved]


def test_listings_whose_portal_hides_the_address_are_flagged_as_approximate(fake_sites, tmp_path):
    # Zap fixture listings with isApproximateLocation: their point is a rounded placeholder.
    approximate = ("2902205200", "2918324333", "2918845046", "2919013171", "2919113143")
    saved = scrape_into(tmp_path, "out", "-C", FAMED, "-m", "1", "-r", "50")

    flagged = {a["link"] for a in saved if a["approximate_location"] is True}
    assert flagged
    assert flagged == {a["link"] for a in saved if any(f"id-{i}/" in a["link"] for i in approximate)}
    assert all(a["approximate_location"] is False for a in saved if a["link"] not in flagged)
    assert "approximate_location" in csv_header(tmp_path, "out")
