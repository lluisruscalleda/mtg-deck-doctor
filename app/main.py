"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import analyses, decks, health
from app.core.config import get_settings
from app.core.exceptions import AppError, NotFoundError, ValidationAppError
from app.core.logging import configure_logging, get_logger
from app.db.session import close_db, init_db

logger = get_logger(__name__)
FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    init_db(settings)
    logger.info("Application starting (env=%s)", settings.app_env)
    yield
    await close_db()
    logger.info("Application stopped")


def create_app() -> FastAPI:
    application = FastAPI(
        title="MTG Deck Doctor",
        description=(
            "Analyze MTG decks with deterministic metrics and grounded LLM recommendations."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.exception_handler(NotFoundError)
    async def not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": exc.message, "code": exc.code})

    @application.exception_handler(ValidationAppError)
    async def validation_handler(_request: Request, exc: ValidationAppError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.message, "code": exc.code})

    @application.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": exc.message, "code": exc.code})

    @application.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    application.include_router(health.router)
    application.include_router(decks.router, prefix="/api/v1")
    application.include_router(analyses.router, prefix="/api/v1")

    if FRONTEND_DIR.exists():
        @application.get("/")
        async def serve_index() -> FileResponse:
            return FileResponse(FRONTEND_DIR / "index.html")

        application.mount(
            "/static",
            StaticFiles(directory=FRONTEND_DIR),
            name="frontend-static",
        )

    return application


app = create_app()


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
    )


if __name__ == "__main__":
    run()
