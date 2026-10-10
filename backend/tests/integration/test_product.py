import base64
import io
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.features.integration.product.app import create_product
from backend.app.features.integration.product.executor import DockerExecutor, ExecutionError
from backend.app.features.integration.product.models import TableInput
from backend.app.features.integration.product.runtime.adapter import (
    AdapterError,
    csv_export,
    decode_pdf,
)
from backend.app.features.integration.proof.independent import fixture_pdf


def payload(**updates):
    data = {'pdf_base64': base64.b64encode(fixture_pdf()).decode(), 'columns': [
        {'name': 'Item', 'type': 'string', 'required': True},
        {'name': 'Quantity', 'type': 'integer', 'required': True},
        {'name': 'Unit price', 'type': 'number', 'required': True}]}
    data.update(updates)
    return TableInput.model_validate(data)


@pytest.mark.parametrize('value,code', [('!', 'INVALID_PDF_ENCODING'),
                                        ('bm90IGEgcGRm', 'INVALID_PDF'),
                                        (base64.b64encode(b'x'*1_000_001).decode(), 'PDF_SIZE_LIMIT')])
def test_decode_bounds(value, code):
    with pytest.raises(AdapterError, match=code):
        decode_pdf(value)


def test_payload_contract_and_csv_safety():
    with pytest.raises(ValidationError):
        payload(columns=[{'name': 'x'}, {'name': 'x'}])
    with pytest.raises(ValidationError):
        payload(columns=[{'name': 'x', 'type': 'execute'}])
    import csv
    rows = list(csv.reader(io.StringIO(csv_export(['x'], [['=cmd'], [' normal'], ['-2']]))))
    assert rows == [['x'], ["'=cmd"], [' normal'], ["'-2"]]


def test_product_api_errors_origin_and_size():
    class Failed:
        async def execute(self, value):
            raise ExecutionError('EXECUTION_TIMEOUT')
    client = TestClient(create_product(Failed()))
    assert client.get('/').status_code == 200
    assert client.get('/assets/other').status_code == 404
    assert client.get('/api/v1/sample').json()['columns'][1]['type'] == 'integer'
    response = client.post('/api/v1/execute', json=payload().model_dump())
    assert response.status_code == 408 and response.json()['detail']['code'] == 'EXECUTION_TIMEOUT'
    assert client.post('/api/v1/execute', json={}, headers={'origin': 'https://evil.invalid'}).status_code == 403
    assert client.post('/api/v1/execute', content='x'*1_500_001).status_code == 413
    assert client.post('/api/v1/execute', json={}).status_code == 422


@pytest.mark.asyncio
async def test_executor_timeout_removes_container(monkeypatch):
    import asyncio
    calls = []
    class Process:
        returncode = None
        async def wait(self):
            self.returncode = -9
        def kill(self):
            calls.append('killed')
    executor = DockerExecutor('sha256:'+'a'*64, timeout=.01)
    async def launch(*args, **kwargs):
        calls.append(args)
        return Process()
    async def exchange(process, data):
        await asyncio.sleep(1)
    async def remove(name):
        calls.append(('removed', name))
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', launch)
    monkeypatch.setattr(executor, '_exchange', exchange)
    monkeypatch.setattr(executor, '_remove', remove)
    with pytest.raises(ExecutionError, match='EXECUTION_TIMEOUT'):
        await executor.execute(payload())
    assert 'killed' in calls and calls[-1][0] == 'removed'
    command = calls[0]
    assert '--network' in command and 'none' in command and '--read-only' in command
    assert '--name' in command and '256m' in command


@pytest.mark.asyncio
async def test_incompatible_output_not_promoted(monkeypatch):
    import asyncio
    class Process:
        returncode = 0
    executor = DockerExecutor('sha256:'+'b'*64)
    async def launch(*args, **kwargs):
        return Process()
    async def exchange(process, data):
        return b'{"result":{"status":"valid"}}'
    async def remove(name):
        pass
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', launch)
    monkeypatch.setattr(executor, '_exchange', exchange)
    monkeypatch.setattr(executor, '_remove', remove)
    with pytest.raises(ExecutionError, match='INCOMPATIBLE_SOURCE_OUTPUT'):
        await executor.execute(payload())


@pytest.mark.skipif(os.environ.get('A_PRODUCT_TESTS') != '1', reason='Explicit local Docker check')
@pytest.mark.asyncio
async def test_real_adapter_known_invalid_and_incompatible():
    image = json.loads(Path('artifacts/integration-product-runtime.json').read_text())['image_id']
    executor = DockerExecutor(image)
    result = await executor.execute(payload())
    assert result.status == 'valid' and result.rows == [['Apples', '2', '1.25'], ['Oranges', '3', '2.00']]
    assert len(result.cells) == 9
    wrong_type = payload().model_dump()
    wrong_type['columns'][0]['type'] = 'integer'
    result = await executor.execute(TableInput.model_validate(wrong_type))
    assert result.status == 'invalid' and result.errors[0].source_cell.row == 2
    assert result.errors[0].source_cell.column == 1 and result.errors[0].source_cell.text == 'Apples'
    blank = fixture_pdf(rows=[('Item', 'Quantity', 'Unit price'), ('Apples', '', '1.25'), ('Oranges', '3', '2.00')])
    missing = await executor.execute(payload(pdf_base64=base64.b64encode(blank).decode()))
    assert missing.status == 'invalid' and missing.errors[0].source_cell.row == 2
    assert missing.errors[0].source_cell.column == 2 and missing.errors[0].source_cell.text == ''
    with pytest.raises(ExecutionError, match='NO_RULED_TABLE'):
        await executor.execute(payload(pdf_base64=base64.b64encode(fixture_pdf(ruled=False)).decode()))
    wrong_header = payload().model_dump()
    wrong_header['columns'][0]['name'] = 'Wrong'
    with pytest.raises(ExecutionError, match='SCHEMA_HEADER_MISMATCH'):
        await executor.execute(TableInput.model_validate(wrong_header))
    with pytest.raises(ExecutionError, match='INVALID_PDF'):
        await executor.execute(payload(pdf_base64=base64.b64encode(b'%PDF-broken').decode()))
    with pytest.raises(ExecutionError, match='EXECUTION_TIMEOUT'):
        await DockerExecutor(image, timeout=.001).execute(payload())


def test_manifest_missing_and_wrong_runtime_are_not_validated(tmp_path):
    from backend.app.features.integration.product.handoff import readiness
    result = readiness(tmp_path)
    assert result.status == 'not_validated_here' and result.version is None


@pytest.mark.asyncio
async def test_output_limit_fails_before_buffering_unbounded_bytes():
    class Stdin:
        def write(self, data):
            pass
        async def drain(self):
            pass
        def close(self):
            pass
    class Stdout:
        reads = 0
        async def read(self, size):
            self.reads += 1
            return b'x' * size
    class Process:
        stdin = Stdin()
        stdout = Stdout()
        async def wait(self):
            pass
    process = Process()
    executor = DockerExecutor('sha256:'+'c'*64)
    with pytest.raises(ExecutionError, match='SOURCE_OUTPUT_LIMIT'):
        await executor._exchange(process, b'{}')
    assert process.stdout.reads == 31


def test_browser_check_requires_visible_output_and_correct_source():
    from backend.app.features.integration.product.checks import EXPECTED_ROWS, evaluate
    observed = {'rows': EXPECTED_ROWS, 'verdict': 'Schema checks passed', 'error_count': 0,
                'selected': {'row': 2, 'column': 2, 'text': '2'}, 'source_detail': 'Page 1'}
    assert evaluate('sourcetable-normal-v1', observed)
    assert not evaluate('sourcetable-normal-v1', {**observed, 'selected': None})
    assert not evaluate('sourcetable-normal-v1', {**observed, 'rows': []})
    assert not evaluate('unknown', observed)
    assert not evaluate('sourcetable-type-error-v1', observed)
