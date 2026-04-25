from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.logging_config import setup_logging
from app.api import actions, onboard, pos, report, history

setup_logging()


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    application = FastAPI(title="VyaparAI Module 1", version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(onboard.router, tags=["onboarding"])
    application.include_router(pos.router, tags=["pos"])
    application.include_router(report.router, tags=["reports"])
    application.include_router(history.router, tags=["history"])
    application.include_router(actions.router, tags=["actions"])
    return application


app = create_app()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a CORS-safe 500 for any unhandled exception."""
    import logging
    logging.getLogger(__name__).error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers={"Access-Control-Allow-Origin": "*"},
    )


@app.get("/")
def root() -> dict:
    """Health check endpoint."""
    return {"status": "VyaparAI Module 1 running"}
