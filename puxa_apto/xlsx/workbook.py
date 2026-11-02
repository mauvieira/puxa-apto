"""Add one styled, filterable sheet of listings to an .xlsx workbook (created if missing).

Built for Google Sheets, Excel 365 and ONLYOFFICE alike, which is why: the Categoria dropdown
points at a hidden `Listas` sheet (other list forms come back from an ONLYOFFICE save as x14
validations that openpyxl drops), links are cell hyperlinks rather than HYPERLINK(), filters carry
no saved criteria, the A1 count is a formula without a cached value, and the font is Arial.
"""

import os
import re
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.properties import PageSetupProperties
from openpyxl.worksheet.worksheet import Worksheet

from ..settings import SearchSettings
from .rows import display_rows


class XlsxExportError(Exception):
    """The workbook can't be written; the message is meant for the user."""


@dataclass(frozen=True)
class SheetOptions:
    title: str  # shown in A1
    places: Dict[str, str]  # distance_km_<slug> key -> place name for its header
    name: str  # wanted sheet name, e.g. "01-11"


@dataclass(frozen=True)
class Column:
    key: str  # in display_rows()
    header: str
    width: int
    kind: str  # "text", "num" (real numbers, so range filters work) or "link"
    number_format: Optional[str] = None  # units live here, never in the value
    bold: bool = False


BRL = '"R$ "#,##0'
METERS = '0" m"'
NEAREST = "distance_km"  # display_rows key of the nearest place's distance
PLACE_PREFIX = "distance_km_"  # display_rows keys of each place's distance
COLUMNS = (
    Column("bairro", "Bairro", 15, "text"),
    Column("rua", "Rua", 28, "text"),
    Column("categoria", "Categoria", 15, "text"),
    Column(NEAREST, "Distância", 10, "num", METERS),  # template for every distance column
    Column("total", "Total", 10, "num", BRL, bold=True),
    Column("aluguel", "Aluguel", 10, "num", BRL),
    Column("condominio", "Condomínio", 11, "num", BRL),
    Column("iptu", "IPTU", 8, "num", BRL),
    Column("area", "Área", 8, "num", '0" m²"'),
    Column("quartos", "Quartos", 8, "num", "0"),
    Column("banheiros", "Banh.", 7, "num", "0"),
    Column("vagas", "Vagas", 7, "num", "0"),
    Column("anuncio", "Anúncio", 9, "link"),
    Column("comodidades", "Comodidades", 26, "text"),
    Column("descricao", "Descrição", 34, "text"),
    Column("fonte", "Fonte", 11, "text"),
    Column("aprox", "Localização aproximada", 22, "text"),
)

LISTAS = "Listas"
CATEGORY_RANGE = f"{LISTAS}!$A$1:$A$4"
# category -> (row fill, chip fill, chip text)
CATEGORIES = {
    "Favoritado": ("FEF7E0", "FDE293", "5C4300"),
    "Em andamento": ("E8F0FE", "AECBFA", "0B3D91"),
    "Talvez": ("FCE4EC", "F8BBD0", "880E4F"),
    "Descartado": ("FCE8E6", "F6AEA9", "8C1D18"),
}
DISCARDED_TEXT = "9AA0A6"
NEAREST_COLOR = "C9EDE0"  # Distância heat map: closest is greenest, farthest white

FONT = "Arial"  # Roboto renders garbled in ONLYOFFICE
TEXT_COLOR = "202124"
LINK_TEXT = "Abrir ↗"
FIRST_ROW = 3  # row 1: count line, row 2: header
FILTER_BUTTON = 3  # extra width so the filter button doesn't cover the header
_HORIZONTAL = {"num": "right", "link": "center", "text": "left"}
_SHEET_NAME_BAD = re.compile(r"[\[\]:*?/\\]")
_SHEET_NAME_MAX = 31
_UNREADABLE = (zipfile.BadZipFile, InvalidFileException, KeyError, OSError)

_GRID = Side(style="thin", color="E0E0E0")
_CELL_BORDER = Border(left=_GRID, right=_GRID, top=_GRID, bottom=_GRID)
_HEADER_BORDER = Border(
    left=Side(style="thin", color="FFFFFF"),
    right=Side(style="thin", color="FFFFFF"),
    bottom=Side(style="thick", color="BDBDBD"),
)
_HEADER_FILL = PatternFill(fill_type="solid", fgColor="FFFFFF")


def sheet_title(settings: Optional[SearchSettings]) -> str:
    """A1 heading: the search's `title`, else "Aluguel · Porto Alegre"-style."""
    if settings is None:
        return "Anúncios"
    if settings.title:
        return settings.title
    kind = "Aluguel" if settings.transaction == "aluguel" else "Venda"
    return f"{kind} · {settings.city}" if settings.city else kind


def _open(path: Path) -> Optional[Workbook]:
    """The workbook at `path`, None when there is none yet; XlsxExportError when it can't be one."""
    if path.suffix.lower() != ".xlsx":
        raise XlsxExportError(f"Excel output must be an .xlsx file: {path}")
    if not path.parent.is_dir():
        raise XlsxExportError(f"Folder not found: {path.parent}")
    if not path.exists():
        return None
    try:
        return openpyxl.load_workbook(path)
    except _UNREADABLE as err:
        raise XlsxExportError(f"Not a readable .xlsx workbook: {path}") from err


def check_workbook(path: Path) -> None:
    """Raise XlsxExportError if `path` can't take a sheet, before any work is done for it."""
    _open(path)


def _sheet_name(wb: Workbook, wanted: str) -> str:
    """`wanted` made legal, with " (2)", " (3)"... when another sheet already has it."""
    base = _SHEET_NAME_BAD.sub("-", wanted).strip()[:_SHEET_NAME_MAX] or "Anúncios"
    taken = {name.lower() for name in wb.sheetnames}
    name, n = base, 2
    while name.lower() in taken:
        suffix = f" ({n})"
        name, n = base[: _SHEET_NAME_MAX - len(suffix)] + suffix, n + 1
    return name


def _new_sheet(wb: Workbook, name: str) -> Worksheet:
    """A first, selected sheet; the others are unselected so Excel doesn't open them grouped."""
    ws = wb.create_sheet(name, 0)
    for sheet in wb.worksheets:
        sheet.sheet_view.tabSelected = False
    ws.sheet_view.tabSelected = True
    wb.active = 0
    if LISTAS not in wb.sheetnames:
        wb.create_sheet(LISTAS)
    listas = wb[LISTAS]
    assert isinstance(listas, Worksheet)
    for row, category in enumerate(CATEGORIES, start=1):
        listas.cell(row=row, column=1, value=category)
    listas.sheet_state = "hidden"
    return ws


def _distance_columns(template: Column, rows: List[Dict[str, Any]], places: Dict[str, str]) -> List[Column]:
    """One column per place some listing has a distance to, after the nearest place's column. The
    nearest is left out when it would repeat the only place, or when no listing has a distance."""
    per_place = [
        replace(template, key=k, header=f"Distância até {_place_name(k, places)}") for k in _place_keys(rows)
    ]
    if len(per_place) == 1 or all(row[NEAREST] is None for row in rows):
        return per_place
    nearest = replace(template, header="Distância (mais próxima)" if per_place else "Distância")
    return [nearest, *per_place]


def _place_keys(rows: List[Dict[str, Any]]) -> List[str]:
    """The distance_km_<slug> keys some row has a distance under, in first-seen order."""
    keys = (k for row in rows for k, v in row.items() if k.startswith(PLACE_PREFIX) and v is not None)
    return list(dict.fromkeys(keys))


def _place_name(key: str, places: Dict[str, str]) -> str:
    """The search's name for the place; without a config, "distance_km_campus_saude" -> "Campus Saude"."""
    return places.get(key) or key.removeprefix(PLACE_PREFIX).replace("_", " ").title()


def _columns(rows: List[Dict[str, Any]], places: Dict[str, str]) -> List[Column]:
    """COLUMNS, with the Distância template expanded into the distance columns the listings have."""
    columns: List[Column] = []
    for c in COLUMNS:
        columns.extend(_distance_columns(c, rows, places) if c.key == NEAREST else [c])
    return columns


def _write_header(ws: Worksheet, columns: List[Column], title: str, count: int) -> None:
    link = get_column_letter(next(i for i, c in enumerate(columns, start=1) if c.kind == "link"))
    last = FIRST_ROW + count - 1
    plural = "s" if count != 1 else ""
    heading = title.replace('"', '""')
    # No cached value: ONLYOFFICE then computes it, and it follows the filter.
    ws["A1"] = f'="{heading}  ·  "&SUBTOTAL(103,{link}{FIRST_ROW}:{link}{last})&" de {count} anúncio{plural}"'
    ws["A1"].font = Font(name=FONT, size=10, bold=True, color="5F6368")
    ws.row_dimensions[1].height = 20
    for index, column in enumerate(columns, start=1):
        cell = ws.cell(row=2, column=index, value=column.header)
        cell.font = Font(name=FONT, size=10, bold=True, color=TEXT_COLOR)
        cell.fill = _HEADER_FILL
        cell.border = _HEADER_BORDER
        cell.alignment = Alignment(
            horizontal=_HORIZONTAL[column.kind],
            vertical="center",
            indent=0 if column.kind == "link" else 1,
        )
        width = max(column.width, len(column.header) + 1) + FILTER_BUTTON
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.row_dimensions[2].height = 26


def _data_style(column: Column) -> Tuple[Font, Alignment]:
    """Font and alignment shared by every data cell of `column`."""
    if column.kind == "link":
        font = Font(name=FONT, size=10, bold=True, color="137333")
    else:
        font = Font(name=FONT, size=10, bold=column.bold, color=TEXT_COLOR)
    indent = 1 if column.kind == "text" else 0
    alignment = Alignment(horizontal=_HORIZONTAL[column.kind], vertical="center", wrap_text=False, indent=indent)
    return font, alignment


def _write_rows(ws: Worksheet, columns: List[Column], rows: List[Dict[str, Any]]) -> None:
    styles = [_data_style(c) for c in columns]
    for row_index, row in enumerate(rows, start=FIRST_ROW):
        ws.row_dimensions[row_index].height = 21
        for col_index, (column, (font, alignment)) in enumerate(zip(columns, styles, strict=True), start=1):
            value = None if row[column.key] == "" else row[column.key]
            link = column.kind == "link" and value is not None
            cell = ws.cell(row=row_index, column=col_index, value=LINK_TEXT if link else value)
            cell.border, cell.font, cell.alignment = _CELL_BORDER, font, alignment
            if column.number_format:
                cell.number_format = column.number_format
            if link:
                cell.hyperlink = value


def _add_rules(ws: Worksheet, columns: List[Column], last: int) -> None:
    """Categoria dropdown, category colours and the distance heat maps."""
    keys = [c.key for c in columns]
    category = get_column_letter(keys.index("categoria") + 1)
    categories = f"{category}{FIRST_ROW}:{category}{last}"
    dropdown = DataValidation(
        type="list",
        formula1=CATEGORY_RANGE,
        allow_blank=True,
        showErrorMessage=True,
        errorTitle="Categoria",
        error="Escolha Favoritado, Em andamento, Talvez ou Descartado.",
    )
    dropdown.add(categories)
    ws.add_data_validation(dropdown)

    def is_(name: str) -> List[str]:
        return [f'${category}{FIRST_ROW}="{name}"']

    # Added in priority order: chip, heat maps, then the whole-row fill.
    for name, (_, chip, chip_text) in CATEGORIES.items():
        chip_fill = PatternFill(fill_type="solid", bgColor=chip)
        rule = FormulaRule(formula=is_(name), fill=chip_fill, font=Font(bold=True, color=chip_text), stopIfTrue=True)
        ws.conditional_formatting.add(categories, rule)
    for index, key in enumerate(keys, start=1):
        if key.startswith(NEAREST):
            distance = get_column_letter(index)
            heat = ColorScaleRule(start_type="min", start_color=NEAREST_COLOR, end_type="max", end_color="FFFFFF")
            ws.conditional_formatting.add(f"{distance}{FIRST_ROW}:{distance}{last}", heat)
    whole_rows = f"A{FIRST_ROW}:{get_column_letter(len(columns))}{last}"
    for name, (row_fill, _, _) in CATEGORIES.items():
        font = Font(color=DISCARDED_TEXT) if name == "Descartado" else None
        rule = FormulaRule(formula=is_(name), fill=PatternFill(fill_type="solid", bgColor=row_fill), font=font)
        ws.conditional_formatting.add(whole_rows, rule)


def _set_up_sheet(ws: Worksheet, columns: List[Column], last: int) -> None:
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A3"
    ws.auto_filter.ref = f"A2:{get_column_letter(len(columns))}{last}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = "2:2"


def append_listings_sheet(path: Path, listings: List[Dict], options: SheetOptions) -> str:
    """Add a sheet of `listings` as the first tab of the workbook at `path`; return its name.

    The workbook is written to a temporary sibling and then moved over `path`, so a failure never
    leaves the user's workbook truncated."""
    if not listings:
        raise XlsxExportError("No listings to export")
    wb = _open(path)
    if wb is None:
        wb = openpyxl.Workbook()
        wb.remove(wb.worksheets[0])
    ws = _new_sheet(wb, _sheet_name(wb, options.name))

    rows = display_rows(listings)
    columns = _columns(rows, options.places)
    last = FIRST_ROW + len(rows) - 1
    _write_header(ws, columns, options.title, len(rows))
    _write_rows(ws, columns, rows)
    _add_rules(ws, columns, last)
    _set_up_sheet(ws, columns, last)

    temporary = path.with_name(f".{path.name}.tmp")
    try:
        wb.save(temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return ws.title
