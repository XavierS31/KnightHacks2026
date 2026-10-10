"""Explicit live validation and immutable handoff freeze; no HF calls."""
import asyncio
import base64
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from backend.app.features.integration.product.executor import (
    DockerExecutor,
    ExecutionError,
    configured_executor,
)
from backend.app.features.integration.product.handoff import (
    MANIFEST,
    ROOT,
    FixedCheck,
    ProductHandoff,
)
from backend.app.features.integration.product.models import TableInput, TableOutput
from backend.app.features.integration.proof.independent import fixture_pdf
from backend.app.shared.contracts import Capability, Evidence, ProductVersion
from backend.app.shared.settings import Settings

PINS = {'jsvine/pdfplumber': '4c64b92d5caccd71c645e98e0fabb0c4dba7ff45',
        'frictionlessdata/frictionless-py': '2a30fbd5a7d9ace96b121494624b970e56a72a0f'}


def implementation_hashes():
    product = ROOT / 'backend/app/features/integration/product'
    paths = list(product.rglob('*.py')) + list((product / 'runtime').glob('*.lock'))
    paths += [product / 'runtime/Dockerfile', ROOT / 'backend/app/features/integration/proof/independent.py']
    paths += list((ROOT / 'frontend/src/features/integration/product').glob('*'))
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(paths) if path.is_file()}


async def validate_and_freeze():
    settings = Settings()
    executor = configured_executor(settings.artifact_root)
    installed_script = "import json,hashlib; from importlib.metadata import distribution; print(json.dumps({'adapter':hashlib.sha256(open('/app/adapter.py','rb').read()).hexdigest(),'sources':{p:json.loads(distribution(p).read_text('direct_url.json')) for p in ['pdfplumber','frictionless']}}))"
    installed = json.loads(subprocess.check_output(
        ['docker', 'run', '--rm', '--pull', 'never', '--network', 'none', '--read-only',
         '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '256m',
         '--cpus', '1', '--pids-limit', '64', '--log-driver', 'none', '--entrypoint', 'python',
         executor.image_id, '-c', installed_script], cwd=ROOT, timeout=15))
    assert installed['adapter'] == hashlib.sha256((Path(__file__).parent / 'runtime/adapter.py').read_bytes()).hexdigest()
    for package, repository in [('pdfplumber', 'jsvine/pdfplumber'), ('frictionless', 'frictionlessdata/frictionless-py')]:
        assert installed['sources'][package]['url'] == f'https://github.com/{repository}/archive/{PINS[repository]}.tar.gz'
    columns = [{'name': 'Item', 'type': 'string', 'required': True},
               {'name': 'Quantity', 'type': 'integer', 'required': True},
               {'name': 'Unit price', 'type': 'number', 'required': True}]
    sample = TableInput(pdf_base64=base64.b64encode(fixture_pdf()).decode(), columns=columns)
    normal = await executor.execute(sample)
    assert normal.status == 'valid' and normal.rows == [['Apples', '2', '1.25'], ['Oranges', '3', '2.00']]
    invalid = sample.model_copy(deep=True)
    invalid.columns[0].type = 'integer'
    rejected = await executor.execute(invalid)
    assert rejected.status == 'invalid'
    assert rejected.errors[0].source_cell.row == 2 and rejected.errors[0].source_cell.column == 1
    missing_pdf = fixture_pdf(rows=[('Item', 'Quantity', 'Unit price'), ('Apples', '', '1.25'), ('Oranges', '3', '2.00')])
    missing = await executor.execute(sample.model_copy(update={'pdf_base64': base64.b64encode(missing_pdf).decode()}))
    assert missing.status == 'invalid' and missing.errors[0].source_cell.column == 2
    incompatible = sample.model_copy(deep=True)
    incompatible.columns[0].name = 'Wrong'
    for case, expected in [
        (incompatible, 'SCHEMA_HEADER_MISMATCH'),
        (sample.model_copy(update={'pdf_base64': base64.b64encode(b'%PDF-broken').decode()}), 'INVALID_PDF'),
        (sample.model_copy(update={'pdf_base64': base64.b64encode(fixture_pdf(ruled=False)).decode()}), 'NO_RULED_TABLE'),
    ]:
        try:
            await executor.execute(case)
        except ExecutionError as failure:
            assert failure.code == expected
        else:
            raise AssertionError('Rejection check failed')
    try:
        await DockerExecutor(executor.image_id, timeout=.001).execute(sample)
    except ExecutionError as failure:
        assert failure.code == 'EXECUTION_TIMEOUT'
    else:
        raise AssertionError('Timeout check failed')
    hashes = implementation_hashes()
    git_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    # Require all implementation bytes to be committed before freezing a version.
    for path in hashes:
        committed = subprocess.check_output(['git', 'show', f'{git_sha}:{path}'], cwd=ROOT)
        assert hashlib.sha256(committed).hexdigest() == hashes[path], 'Commit implementation before freeze'
    key = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    identity = uuid5(NAMESPACE_URL, f'repofusion-sourcetable-v1:{key}')
    evidence = [Evidence(source=name, reference=f'https://github.com/{name}/commit/{sha}',
                         collected_at=datetime.now(UTC), kind='source',
                         note='Pinned source archive installed; independent and adapter checks executed locally.')
                for name, sha in PINS.items()]
    limitations = ['Validated on fixed machine-generated ruled PDF fixtures, not arbitrary PDFs or OCR.',
                   'Exactly one table, up to 1 MB/3 pages/100 rows/12 columns; broader cases need review.',
                   'Schema validity is not transcription accuracy, accounting correctness or demand evidence.',
                   'Stateless local operation; no Neon persistence, persona trials, or v2 promotion.',
                   'Source MIT notices are preserved in installed distributions; full dependency review remains open.']
    capability = Capability(id=uuid5(identity, 'extract-validate-table'), key='extract_validate_table',
                            description='Extract a ruled PDF table, validate declared column types, and map errors to source cells.',
                            input_schema=TableInput.model_json_schema(), output_schema=TableOutput.model_json_schema(),
                            validated=True, evidence=evidence)
    handoff = ProductHandoff(
        version=ProductVersion(id=identity, label='SourceTable v1', status='validated', commit_sha=git_sha,
                               runtime_url='http://127.0.0.1:8001', capabilities=[capability],
                               briefing='Load sample PDF, choose column types, then Extract & validate. Inspect a result cell or error to see its original text and source coordinates. Download a display-safe CSV. Reload starts fresh state.',
                               limitations=limitations), source_commits=PINS, image_id=executor.image_id,
        implementation_hashes=hashes, initial_states={'sample-inventory-v1': sample.model_dump(mode='json')},
        checks=[FixedCheck(id='sourcetable-normal-v1', goal='Extract the sample inventory and inspect Quantity in its first row.',
                           initial_state='sample-inventory-v1', expected={'status': 'valid', 'rows': normal.rows,
                                                                       'source_row': 2, 'source_column': 2, 'source_text': '2'}, action_budget=6),
                FixedCheck(id='sourcetable-type-error-v1', goal='Set the Item column to integer, run the check, and inspect the first error.',
                           initial_state='sample-inventory-v1', expected={'status': 'invalid', 'source_row': 2,
                                                                       'source_column': 1, 'source_text': 'Apples'}, action_budget=7),
                FixedCheck(id='sourcetable-recovery-v1', goal='After an Item integer error, change Item back to string and rerun.',
                           initial_state='sample-inventory-v1', expected={'status': 'valid', 'rows': normal.rows}, action_budget=9)],
        validation={'validated_at': datetime.now(UTC).isoformat(), 'normal': 'passed', 'invalid_type': 'passed',
                    'missing_value': 'passed', 'header_mismatch': 'passed', 'malformed_pdf': 'passed',
                    'no_table': 'passed', 'timeout_cleanup': 'passed', 'fixture_pdf_sha256': normal.pdf_sha256,
                    'installed_sources': installed,
                    'environment': 'Linux arm64, Python 3.12; immutable local image; pinned dependency versions'},
        limitations=limitations,
    )
    MANIFEST.parent.mkdir(exist_ok=True)
    if MANIFEST.exists():
        previous = ProductHandoff.model_validate_json(MANIFEST.read_text())
        if previous.version.id != identity or previous.image_id != executor.image_id:
            raise SystemExit('Preserve v1; freeze changed code/environment as another reviewed version instead.')
        print('Checks passed again; preserved the existing immutable v1 manifest.')
        return
    MANIFEST.write_text(handoff.model_dump_json(indent=2)+'\n')
    (settings.artifact_root / 'product-validation-normal.json').write_text(normal.model_dump_json(indent=2))
    (settings.artifact_root / 'product-validation-invalid.json').write_text(rejected.model_dump_json(indent=2))
    print('Validated fixed checks and froze SourceTable v1:', git_sha)


if __name__ == '__main__':
    asyncio.run(validate_and_freeze())
