"""Known independent fixtures, not an adapter or a generated product."""
import csv
import io
import json
import sys
from importlib.metadata import distribution, version
from pathlib import Path


def fixture_pdf(rows=None, ruled=True):
    # A machine-generated one-page table with explicit ruling lines and ASCII cells.
    content = ['0.5 w']
    if ruled:
        for x in [50, 250, 330, 430]:
            content.append(f'{x} 650 m {x} 740 l S')
        for y in [650, 680, 710, 740]:
            content.append(f'50 {y} m 430 {y} l S')
    rows = rows or [('Item', 'Quantity', 'Unit price'), ('Apples', '2', '1.25'), ('Oranges', '3', '2.00')]
    for row, y in zip(rows, [720, 690, 660], strict=True):
        for text, x in zip(row, [60, 260, 340], strict=True):
            escaped = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
            content.append(f'BT /F1 12 Tf {x} {y} Td ({escaped}) Tj ET')
    stream = '\n'.join(content).encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               f'<< /Length {len(stream)} >>\nstream\n'.encode() + stream + b'\nendstream']
    output = b'%PDF-1.4\n'
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output += f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(output)
    output += f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
    output += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    output += f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    return output


def pdf_check():
    import pdfplumber
    expected = [['Item', 'Quantity', 'Unit price'], ['Apples', '2', '1.25'], ['Oranges', '3', '2.00']]
    with pdfplumber.open(io.BytesIO(fixture_pdf())) as pdf:
        actual = pdf.pages[0].extract_table()
        assert actual == expected, actual
        boxes = pdf.pages[0].find_tables()[0].cells
        assert len(boxes) == 9
    rejected = False
    try:
        pdfplumber.open(io.BytesIO(b'not a PDF'))
    except Exception:
        rejected = True
    assert rejected
    return {'rows': actual, 'cell_count': len(boxes), 'invalid_pdf_rejected': rejected,
            'units': 'PDF points; row positions are not validation coordinates yet'}


def schema_check():
    from frictionless import Resource, Schema
    schema = Schema.from_descriptor({'fields': [
        {'name': 'Item', 'type': 'string', 'constraints': {'required': True}},
        {'name': 'Quantity', 'type': 'integer', 'constraints': {'minimum': 1}},
        {'name': 'Unit price', 'type': 'number', 'constraints': {'minimum': 0}},
    ]})
    path = Path('known-table.csv')
    results = []
    for quantity in ['2', 'invalid']:
        with path.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerows([['Item', 'Quantity', 'Unit price'], ['Apples', quantity, '1.25'], ['Oranges', '3', '2.00']])
        report = Resource(path=str(path), schema=schema).validate()
        results.append({'valid': report.valid, 'errors': report.flatten(['type', 'rowNumber', 'fieldName'])})
    assert results[0]['valid'] is True, results
    assert results[1]['valid'] is False and results[1]['errors'], results
    return {'valid_fixture': results[0], 'invalid_integer_fixture': results[1],
            'semantics': 'Schema validity, not correctness of PDF transcription or totals'}


def main():
    operation = sys.argv[1]
    package = {'pdf': 'pdfplumber', 'schema': 'frictionless'}[operation]
    result = (pdf_check if operation == 'pdf' else schema_check)()
    print(json.dumps({'source': package, 'version': version(package),
                      'installed_source': json.loads(distribution(package).read_text('direct_url.json')),
                      'checks': result}, indent=2))


if __name__ == '__main__':
    main()
