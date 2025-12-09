from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.api import api_router
from app.services.scheduler import start_scheduler
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application starting up...")
    start_scheduler()
    yield
    # Shutdown
    logger.info("Application shutting down...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan
)

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")

# 注册路由
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {
        "message": "BrandMonitor API is running",
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }