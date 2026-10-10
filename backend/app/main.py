from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.features.evolution.router import router as evolution_router
from backend.app.features.integration.router import router as integration_router
from backend.app.features.personas.router import router as personas_router
from backend.app.shared.contracts import ErrorDetail, ErrorResponse, StreamEvent
from backend.app.shared.settings import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="RepoFusion API", version="0.1.0",
                  description="Fixture-first scaffold; real integration and experiment gates remain required.")
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        details = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        error = ErrorResponse(error=ErrorDetail(code=details.get("code", "REQUEST_FAILED"),
                                              message=details.get("message", "Request failed"),
                                              retryable=details.get("retryable", False)),
                              request_id=str(uuid4()))
        return JSONResponse(status_code=exc.status_code, content=error.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        error = ErrorResponse(error=ErrorDetail(code="VALIDATION_ERROR", message="Request does not match the contract.",
                                              details={"errors": [{"location": list(e["loc"]), "message": e["msg"]} for e in exc.errors()]}),
                              request_id=str(uuid4()))
        return JSONResponse(status_code=422, content=error.model_dump(mode="json"))

    @app.get("/api/v1/health", tags=["system"])
    def health():
        settings = get_settings()
        return {"status": "ok", "mode": settings.app_mode,
                "inference_configured": bool(settings.hf_token.get_secret_value() and settings.hf_model_id and settings.hf_provider),
                "database_configured": bool(settings.database_url.get_secret_value()),
                "population_target": 500, "featured_personas": 10}

    # Expose WebSocket envelope to generated types without inventing a HTTP stream implementation.
    @app.get("/api/v1/contracts/stream-event", response_model=StreamEvent, tags=["contracts"])
    def stream_contract():
        raise HTTPException(status_code=409, detail={"code": "SCHEMA_ONLY", "message": "Use the session WebSocket for events."})

    app.include_router(integration_router, prefix="/api/v1")
    app.include_router(personas_router, prefix="/api/v1")
    app.include_router(evolution_router, prefix="/api/v1")
    return app


app = create_app()
