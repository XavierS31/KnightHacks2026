"""Separate loopback product process. Stateless requests; no fixture inference."""
import base64
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from backend.app.features.integration.product.executor import ExecutionError, configured_executor
from backend.app.features.integration.product.handoff import ProductHandoff, verified_handoff
from backend.app.features.integration.product.models import TableInput, TableOutput
from backend.app.features.integration.proof.independent import fixture_pdf
from backend.app.shared.settings import Settings

FRONTEND = Path(__file__).resolve().parents[5] / 'frontend/src/features/integration/product'


def create_product(executor=None):
    app = FastAPI(title='SourceTable — RepoFusion product v1')

    @app.middleware('http')
    async def local_requests(request: Request, call_next):
        if request.client and request.client.host not in {'127.0.0.1', '::1', 'testclient'}:
            return JSONResponse({'error': {'code': 'LOCAL_ONLY'}}, status_code=403)
        origin = request.headers.get('origin')
        if origin and origin not in {'http://127.0.0.1:8001', 'http://localhost:8001'}:
            return JSONResponse({'error': {'code': 'ORIGIN_REJECTED'}}, status_code=403)
        if request.method == 'POST':
            size = request.headers.get('content-length')
            if not size or not size.isdigit() or int(size) > 1_500_000:
                return JSONResponse({'error': {'code': 'REQUEST_SIZE_LIMIT'}}, status_code=413)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/')
    def index():
        return FileResponse(FRONTEND / 'index.html')

    @app.get('/assets/{name}')
    def asset(name: str):
        if name not in {'app.js', 'style.css'}:
            raise HTTPException(404)
        return FileResponse(FRONTEND / name)

    @app.get('/api/v1/sample')
    def sample():
        return {'pdf_base64': base64.b64encode(fixture_pdf()).decode(),
                'columns': [{'name': 'Item', 'type': 'string', 'required': True},
                            {'name': 'Quantity', 'type': 'integer', 'required': True},
                            {'name': 'Unit price', 'type': 'number', 'required': True}]}

    @app.get('/api/v1/handoff', response_model=ProductHandoff)
    def handoff():
        try:
            return verified_handoff(Settings().artifact_root)
        except ExecutionError as failure:
            raise HTTPException(409, detail={'code': failure.code}) from None

    @app.post('/api/v1/execute', response_model=TableOutput)
    async def execute(payload: TableInput):
        nonlocal executor
        try:
            if executor is None:
                executor = configured_executor(Settings().artifact_root)
            return await executor.execute(payload)
        except ExecutionError as failure:
            raise HTTPException(408 if failure.code == 'EXECUTION_TIMEOUT' else 422,
                                detail={'code': failure.code}) from None

    return app


app = create_product()
