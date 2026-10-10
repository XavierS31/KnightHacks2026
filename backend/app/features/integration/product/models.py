"""Feature-local operation contracts; the product is stateless between requests."""
import math
from typing import Literal

from pydantic import Field, model_validator

from backend.app.shared.contracts import Contract

MAX_PDF_BYTES = 1_000_000


class ColumnRule(Contract):
    name: str = Field(min_length=1, max_length=80)
    type: Literal['string', 'integer', 'number', 'date'] = 'string'
    required: bool = False


class TableInput(Contract):
    pdf_base64: str = Field(min_length=1, max_length=1_333_336)
    columns: list[ColumnRule] = Field(min_length=1, max_length=12)

    @model_validator(mode='after')
    def unique_names(self):
        if len({c.name for c in self.columns}) != len(self.columns):
            raise ValueError('Column names must be distinct')
        return self


class Cell(Contract):
    page: int = Field(ge=1, le=3)
    table: int = Field(ge=0)
    row: int = Field(ge=1)
    column: int = Field(ge=1)
    text: str = Field(max_length=500)
    bbox: tuple[float, float, float, float] | None

    @model_validator(mode='after')
    def finite_geometry(self):
        if self.bbox is not None and not all(math.isfinite(value) for value in self.bbox):
            raise ValueError('Cell coordinates must be finite')
        return self


class TableError(Contract):
    code: str
    message: str
    row: int | None = None
    column: int | None = None
    source_cell: Cell | None = None


class TableOutput(Contract):
    status: Literal['valid', 'invalid']
    headers: list[str]
    rows: list[list[str]]
    cells: list[Cell]
    errors: list[TableError]
    csv_text: str
    pdf_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    limitations: list[str]
