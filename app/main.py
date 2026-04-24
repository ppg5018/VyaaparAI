from fastapi import FastAPI

from app.logging_config import setup_logging
from app.api import onboard, pos, report, history

setup_logging()


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    application = FastAPI(title="VyaparAI Module 1", version="0.1.0")
    application.include_router(onboard.router, tags=["onboarding"])
    application.include_router(pos.router, tags=["pos"])
    application.include_router(report.router, tags=["reports"])
    application.include_router(history.router, tags=["history"])
    return application


app = create_app()


@app.get("/")
def root() -> dict:
    """Health check endpoint."""
    return {"status": "VyaparAI Module 1 running"}
