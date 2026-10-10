"""Runs inside the offline source container. Only bounded PDF -> schema validation."""
import base64
import binascii
import csv
import hashlib
import io
import json
from pathlib import Path

MAX_BYTES = 1_000_000


class AdapterError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def decode_pdf(value):
    try:
        data = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise AdapterError('INVALID_PDF_ENCODING') from None
    if not data or len(data) > MAX_BYTES:
        raise AdapterError('PDF_SIZE_LIMIT')
    if not data.startswith(b'%PDF-'):
        raise AdapterError('INVALID_PDF')
    return data


def csv_export(headers, rows):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    # Spreadsheet viewers can execute formula-prefixed values. This export is a
    # display-safe derivative, distinct from the exact raw strings used by checks.
    def safe(value):
        return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value
    writer.writerow([safe(value) for value in headers])
    writer.writerows([[safe(value) for value in row] for row in rows])
    return output.getvalue()


def validate_rows(headers, rows, rules):
    from frictionless import Resource, Schema
    path = Path('table.csv')
    with path.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerows([headers, *rows])
    schema = Schema.from_descriptor({'fields': [
        {'name': rule['name'], 'type': rule['type'],
         'constraints': {'required': rule['required']}}
        for rule in rules
    ]})
    return Resource(path=str(path), schema=schema).validate()


def execute(payload):
    import pdfplumber
    data = decode_pdf(payload['pdf_base64'])
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > 3:
                raise AdapterError('PAGE_LIMIT')
            tables = [(number, table) for number, page in enumerate(pdf.pages, 1)
                      for table in page.find_tables()]
            if not tables:
                raise AdapterError('NO_RULED_TABLE')
            if len(tables) != 1:
                raise AdapterError('MULTIPLE_TABLES')
            page, table = tables[0]
            raw = table.extract()
            if not raw or len(raw) < 2 or not 1 <= len(raw[0]) <= 12 or len(raw) > 101:
                raise AdapterError('TABLE_SIZE_LIMIT')
            if any(len(row) != len(raw[0]) for row in raw):
                raise AdapterError('INCOMPATIBLE_TABLE')
            rows = [[text or '' for text in row] for row in raw]
            if any(len(text) > 500 for row in rows for text in row):
                raise AdapterError('CELL_SIZE_LIMIT')
            headers = rows[0]
            if len(set(headers)) != len(headers) or any(not h.strip() for h in headers):
                raise AdapterError('AMBIGUOUS_HEADERS')
            if headers != [rule['name'] for rule in payload['columns']]:
                raise AdapterError('SCHEMA_HEADER_MISMATCH')
            cells = [{'page': page, 'table': 0, 'row': r + 1, 'column': c + 1,
                      'text': text, 'bbox': table.rows[r].cells[c]}
                     for r, row in enumerate(rows) for c, text in enumerate(row)]
    except AdapterError:
        raise
    except Exception:
        raise AdapterError('INVALID_PDF') from None
    report = validate_rows(headers, rows[1:], payload['columns'])
    errors = []
    for kind, message, row, column in report.flatten(['type', 'message', 'rowNumber', 'fieldNumber']):
        source = next((cell for cell in cells if cell['row'] == row and cell['column'] == column), None)
        errors.append({'code': kind, 'message': message[:500], 'row': row, 'column': column,
                       'source_cell': source})
    return {'status': 'valid' if report.valid else 'invalid', 'headers': headers,
            'rows': rows[1:], 'cells': cells, 'errors': errors,
            'csv_text': csv_export(headers, rows[1:]), 'pdf_sha256': hashlib.sha256(data).hexdigest(),
            'limitations': ['Machine-generated ruled PDFs only; no OCR. Exactly one table, up to three pages.',
                            'Types validate extracted text; they do not prove faithful transcription.',
                            'Blank cells become empty strings and use Frictionless missing-value semantics.',
                            'Source boxes use PDF points with a top-origin y coordinate; rows include the header.',
                            'CSV export prefixes formula-like text with an apostrophe; source text is unchanged.']}


if __name__ == '__main__':
    import sys
    try:
        payload = json.loads(sys.stdin.read(1_500_001))
        print(json.dumps({'result': execute(payload)}))
    except AdapterError as failure:
        print(json.dumps({'error': failure.code}))
    except Exception:
        print(json.dumps({'error': 'ADAPTER_FAILED'}))
