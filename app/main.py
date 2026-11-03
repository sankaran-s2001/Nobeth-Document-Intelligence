import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import config
from app.database.database import init_db, cleanup_expired_jobs
from app.api.routes import router
from app.services.gemini_service import GeminiService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nobeth.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Nobeth Document Intelligence...")
    config.ensure_directories()
    init_db()
    expired_count = cleanup_expired_jobs()
    if expired_count > 0:
        logger.info("Cleaned up %d expired jobs on startup.", expired_count)

    if GeminiService.is_configured():
        logger.info(
            "Gemini AI client ready (Primary: %s, Fallback: %s)",
            config.gemini_primary_model,
            config.gemini_fallback_model,
        )
    else:
        logger.warning(
            "GEMINI_API_KEY is not set in .env. AI extraction will remain disabled until configured."
        )

    yield

    # Shutdown
    logger.info("Shutting down Nobeth Document Intelligence.")


app = FastAPI(
    title="Nobeth Document Intelligence",
    description="Enterprise AI Document Understanding & Handwriting Transcription Platform by Nobeth Analytics",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware (Supports local desktop & cloud deployments e.g., Render)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Assets & Templates
app.mount("/static", StaticFiles(directory=str(config.static_dir)), name="static")
templates = Jinja2Templates(directory=str(config.templates_dir))

# Include API Router
app.include_router(router)


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "product_name": "Nobeth Document Intelligence",
            "organization": "Nobeth Analytics",
            "gemini_configured": GeminiService.is_configured(),
            "primary_model": config.gemini_primary_model,
            "fallback_model": config.gemini_fallback_model,
            "gemini_data_mode": config.gemini_data_mode,
            "max_upload_mb": config.max_upload_mb,
            "max_pdf_pages": config.max_pdf_pages,
            "retention_hours": config.job_retention_hours,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error processing %s: %s", request.url.path, exc, exc_info=True)
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal error occurred during document processing. Please check server logs."
            },
        )
    return HTMLResponse(
        content="<h2>Nobeth Document Intelligence</h2><p>An unexpected error occurred. Please refresh or retry.</p>",
        status_code=500,
    )
