import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet
from typer.testing import CliRunner

from puxa_apto.cli import app
from puxa_apto.utils.storage import save_to_csv

FAMED = str(Path(__file__).resolve().parent / "fixtures" / "famed.json")
VIVAREAL_LINK = "https://www.vivareal.com.br/imovel/apartamento-1-quarto-santa-cecilia-porto-alegre-45m2-aluguel-id-1/"
ZAP_LINK = "https://www.zapimoveis.com.br/imovel/aluguel-apartamento-1-quarto-santa-cecilia-porto-alegre-40m2-id-2/"
LEINDECKER_LINK = "https://www.leindecker.com.br/imovel/apartamento-bom-fim-porto-alegre/1234/"
HEADERS = [
    "Bairro",
    "Rua",
    "Categoria",
    "Distância (mais próxima)",
    "Distância até Famed",
    "Distância até HCPA",
    "Distância até HPS",
    "Distância até Campus Saúde",
    "Total",
    "Aluguel",
    "Condomínio",
    "IPTU",
    "Área",
    "Quartos",
    "Banh.",
    "Vagas",
    "Anúncio",
    "Comodidades",
    "Descrição",
    "Fonte",
    "Localização aproximada",
]


def invoke(*args):
    # setup_logging binds a handler to the previous run's captured stdout; start each run clean.
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    return CliRunner().invoke(app, list(args))


def run(*args):
    result = invoke(*args)
    assert result.exit_code == 0, result.output
    return result


def listings():
    """Three listings as a scrape saves them: a portal one, a sparse one, an agency one."""
    return [
        {
            "link": VIVAREAL_LINK,
            "street": "Rua Ramiro Barcelos, 1954",
            "neighborhood": "Santa Cecilia",
            "area": 45,
            "bedrooms": 2,
            "bathrooms": 1,
            "parking": None,
            "price": 1700.0,
            "condo_fee": 300.0,
            "iptu": None,
            "total_price": 2000.0,
            "distance_km": None,
            "approximate_location": True,
            "amenity_codes": ["KITCHEN", "PETS_ALLOWED", "Piso Parquet", "Banheiro", "NEW_CODE"],
            "description": "<p>Lindo <b>apto</b></p>\n  perto do HCPA",
        },
        {
            "link": ZAP_LINK,
            "street": "Rua São Manoel, 12",
            "neighborhood": "Santa Cecília",
            "area": 40,
            "bedrooms": 1,
            "parking": 0,
            "price": 1500.0,
            "total_price": None,
            "distance_km": None,
            "approximate_location": False,
        },
        {
            "link": LEINDECKER_LINK,
            "street": "Rua Santana, 300",
            "neighborhood": "Bom Fim",
            "area": 38,
            "bedrooms": 1,
            "parking": 1,
            "price": 1200.0,
            "condo_fee": 300.0,
            "total_price": 1500.0,
            "distance_km": None,
        },
    ]


def with_distances(apartments):
    for km, apt in zip((0.4, 0.9, 1.1), apartments, strict=True):
        apt["distance_km"] = apt["distance_km_famed"] = km
    return apartments


def with_two_places(apartments):
    with_distances(apartments)
    for km, apt in zip((0.3, 1.5, 0.7), apartments, strict=True):
        apt["distance_km_campus_saude"] = km
        apt["distance_km"] = min(apt["distance_km_famed"], km)
    return apartments


def write_json(path, apartments):
    path.write_text(json.dumps(apartments, ensure_ascii=False), encoding="utf-8")
    return str(path)


def sheet(path, name):
    ws = openpyxl.load_workbook(path)[name]
    assert isinstance(ws, Worksheet)
    return ws


def headers(ws):
    return [str(c.value) for c in ws[2]]


def column(ws, header):
    """Data cells (row 3 down) under `header`."""
    index = headers(ws).index(header) + 1
    return [ws.cell(row=r, column=index) for r in range(3, ws.max_row + 1)]


def values(ws, header):
    return [c.value for c in column(ws, header)]


def test_a_scrape_with_xlsx_creates_a_filterable_sheet_of_this_runs_new_listings(fake_sites, tmp_path):
    run("scrape", "-C", FAMED, "-m", "1", "--json", "h.json", "--xlsx", "busca.xlsx")

    saved = json.loads((tmp_path / "h.json").read_text(encoding="utf-8"))
    today = datetime.now().strftime("%d-%m")
    wb = openpyxl.load_workbook(tmp_path / "busca.xlsx")
    assert wb.sheetnames == [today, "Listas"]
    assert wb["Listas"].sheet_state == "hidden"
    ws = sheet(tmp_path / "busca.xlsx", today)
    assert headers(ws) == HEADERS
    anuncios = column(ws, "Anúncio")
    assert len(anuncios) == len(saved)
    assert {c.hyperlink.target for c in anuncios if c.hyperlink} == {a["link"] for a in saved}
    assert ws.auto_filter.ref == f"A2:U{len(saved) + 2}"
    row_of = {c.hyperlink.target: i for i, c in enumerate(anuncios) if c.hyperlink}
    hps, nearest = values(ws, "Distância até HPS"), values(ws, "Distância (mais próxima)")
    for apt in saved:
        meters = None if apt["distance_km_hps"] is None else round(apt["distance_km_hps"] * 1000)
        assert hps[row_of[apt["link"]]] == meters
        assert meters is None or type(hps[row_of[apt["link"]]]) is int
        assert nearest[row_of[apt["link"]]] == round(apt["distance_km"] * 1000)
    assert not list(tmp_path.glob("apartamentos_novos_*.csv"))


def test_adding_a_run_to_a_workbook_keeps_the_users_marks_and_the_dropdown(tmp_path):
    source = write_json(tmp_path / "a.json", listings())
    out = tmp_path / "w.xlsx"
    run("export-xlsx", source, "-o", str(out), "-n", "01-11")
    wb = openpyxl.load_workbook(out)
    first = wb["01-11"]
    assert isinstance(first, Worksheet)
    first["C3"] = "Favoritado"
    wb.save(out)

    run("export-xlsx", source, "-o", str(out), "-n", "01-11")

    assert openpyxl.load_workbook(out).sheetnames == ["01-11 (2)", "01-11", "Listas"]
    assert sheet(out, "01-11")["C3"].value == "Favoritado"
    for name in ("01-11 (2)", "01-11"):
        validations = sheet(out, name).data_validations.dataValidation
        assert [(v.type, v.formula1, str(v.sqref)) for v in validations] == [
            ("list", "Listas!$A$1:$A$4", "C3:C5")
        ]


def test_the_distance_columns_follow_the_searchs_places_in_metres(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "w.xlsx"
    run("export-xlsx", write_json(tmp_path / "far.json", listings()), "-o", str(out), "-n", "far")

    far = sheet(out, "far")
    assert not any(h.startswith("Distância") for h in headers(far))
    assert far["D2"].value == "Total"

    config = tmp_path / "busca.json"
    config.write_text(json.dumps({"places": [{"name": "Famed", "lat": -30.04, "lon": -51.2075}]}), encoding="utf-8")
    near = write_json(tmp_path / "near.json", with_distances(listings()))
    run("export-xlsx", near, "-o", str(out), "-n", "near", "-C", str(config))

    ws = sheet(out, "near")
    assert [h for h in headers(ws) if h.startswith("Distância")] == ["Distância até Famed"]
    assert values(ws, "Distância até Famed") == [1100, 400, 900]
    assert all(type(v) is int for v in values(ws, "Distância até Famed"))
    assert {c.number_format for c in column(ws, "Distância até Famed")} == {'0" m"'}

    run("export-xlsx", write_json(tmp_path / "two.json", with_two_places(listings())), "-o", str(out), "-n", "two")

    two = sheet(out, "two")
    assert [h for h in headers(two) if h.startswith("Distância")] == [
        "Distância (mais próxima)",
        "Distância até Famed",
        "Distância até Campus Saude",
    ]
    assert values(two, "Distância (mais próxima)") == [700, 300, 900]


def test_values_are_readable_and_filterable(tmp_path):
    out = tmp_path / "w.xlsx"
    run("export-xlsx", write_json(tmp_path / "a.json", listings()), "-o", str(out), "-n", "x")

    ws = sheet(out, "x")
    position = {c.hyperlink.target: i for i, c in enumerate(column(ws, "Anúncio")) if c.hyperlink}
    viva, zap = position[VIVAREAL_LINK], position[ZAP_LINK]
    assert values(ws, "Bairro")[viva] == values(ws, "Bairro")[zap] == "Santa Cecília"
    assert values(ws, "Comodidades")[viva] == "Aceita pets, Cozinha, Piso parquet, New code"
    assert values(ws, "Fonte")[viva] == "VivaReal"
    assert values(ws, "IPTU")[viva] is None
    assert values(ws, "Localização aproximada")[viva] == "Sim"
    assert values(ws, "Total") == [1500, 2000, None]
    assert {c.number_format for c in column(ws, "Total")} == {'"R$ "#,##0'}
    for header in ("Área", "Quartos"):
        assert all(type(v) is int for v in values(ws, header))
    assert values(ws, "Vagas")[viva] is None
    assert values(ws, "Vagas")[zap] == 0
    assert type(values(ws, "Vagas")[zap]) is int
    assert "SUBTOTAL(103," in ws["A1"].value
    assert ws["A1"].value.endswith('" de 3 anúncios"')


def test_the_installed_cli_converts_a_scrape_csv_and_refuses_a_non_workbook(tmp_path):
    save_to_csv(with_distances(listings()), str(tmp_path / "l.csv"))

    def export(output):
        command = [sys.executable, "-m", "puxa_apto.cli", "export-xlsx", "l.csv", "-o", output]
        return subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, check=False)

    done = export("out.xlsx")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "added to" in done.stdout
    ws = sheet(tmp_path / "out.xlsx", openpyxl.load_workbook(tmp_path / "out.xlsx").sheetnames[0])
    assert len(column(ws, "Anúncio")) == len(listings())
    assert all(isinstance(v, (int, float)) for v in values(ws, "Total") if v is not None)
    assert any(isinstance(v, (int, float)) for v in values(ws, "Total"))
    famed = values(ws, "Distância até Famed")
    assert famed == [1100, 400, 900]
    assert all(type(v) is int for v in famed)

    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not a zip")
    refused = export("bad.xlsx")
    assert refused.returncode == 2
    assert "Not a readable .xlsx workbook" in refused.stdout + refused.stderr
    assert bad.read_bytes() == b"not a zip"
